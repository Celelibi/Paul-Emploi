import email.message
import email.policy
import logging
import mimetypes
import smtplib
import subprocess



class Mailer(object):
    def __init__(self, host, port=None, authmethod=None, user=None, pwd=None, oauthcmd=None):
        if authmethod is None:
            if pwd and oauthcmd:
                raise ValueError("SMTP password and oauthcmd provided")

            if user and not oauthcmd:
                authmethod = "login"
            elif not pwd and oauthcmd:
                authmethod = "oauth"

        self._host = host
        self._port = port
        self._auth = authmethod
        self._user = user
        self._pass = pwd
        self._oauthcmd = oauthcmd.lower()




    def _oauthcb(self, x=None):
        if x is not None:
            return ""
        logging.debug("Running OAuth token generation command: %s", self._oauthcmd)
        token = subprocess.check_output(self._oauthcmd, shell=True)
        token = token.decode().strip()
        logging.debug("Got token: %s", token)
        auth_string = "user=%s\1auth=Bearer %s\1\1" % (self._user, token)
        return auth_string



    def message(self, to, subj, msg, attachments=None):
        if attachments is None:
            attachments = []

        policy = email.policy.EmailPolicy(raise_on_defect=True, linesep="\r\n", utf8=True)
        mail = email.message.EmailMessage(policy=policy)
        mail['Subject'] = "[BOT Paul Emploi] %s" % subj
        mail['From'] = "Bot Paul-Emploi <%s>" % self._user
        mail['To'] = "Chômeur <%s>" % to
        mail.set_content(msg, disposition='inline')

        for name, content in attachments:
            mime, encoding = mimetypes.guess_type(name)
            if mime is None or encoding is not None:
                mime = "application/octet-stream"

            maintype, subtype = mime.split("/")
            mail.add_attachment(content, maintype=maintype, subtype=subtype, filename=name)

        logging.debug("Connecting to SMTP server %s:%r", self._host, self._port)
        smtp = smtplib.SMTP_SSL(self._host, port=self._port)

        if not self._auth:
            logging.info("No SMTP authentication method provided")
        elif self._auth == "login":
            logging.debug("Login to SMTP server with username: %s", self._user)
            smtp.login(self._user, self._pass)
        elif self._auth == "oauth":
            logging.debug("OAuth to SMTP server with username: %s", self._user)
            smtp.ehlo_or_helo_if_needed()
            smtp.auth("XOAUTH2", self._oauthcb)
        else:
            raise ValueError("Unknown SMTP authentication method " + self._auth)

        logging.debug("Sending message of %d bytes", len(mail.as_bytes()))
        smtp.send_message(mail)
        smtp.quit()



    def error(self, to, msg):
        self.message(to, "Error", msg)
