import email.message
import email.policy
import logging
import mimetypes
import smtplib



class Mailer(object):
    def __init__(self, host, port=None, user=None, pwd=None):
        self._host = host
        self._port = port
        self._user = user
        self._pass = pwd



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

        if self._user is not None and self._pass is not None:
            logging.debug("Login to SMTP server with username: %s", self._user)
            smtp.login(self._user, self._pass)
        else:
            logging.debug("No SMTP login or password provided")

        logging.debug("Sending message of %d bytes", len(mail.as_bytes()))
        smtp.send_message(mail)
        smtp.quit()



    def error(self, to, msg):
        self.message(to, "Error", msg)
