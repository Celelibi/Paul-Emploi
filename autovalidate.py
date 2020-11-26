#!/usr/bin/env python3

import argparse
import calendar
import configparser
import datetime
import email.message
import email.policy
import json
import locale
import logging
import mimetypes
import random
import re
import smtplib
import traceback
import urllib.parse

import lxml.html
import requests



questions = {
    'travailleBloc': "Avez-vous travaillé ou exercé une activité non salariée ?",
    'nbHeuresTravBloc': "Heures travaillées dans le mois",
    'montSalaireBloc': "Montant total de votre ou vos salaires bruts réels ou estimés",
    'stageBloc': "Avez-vous été en stage ?",
    'maladieBloc': "Avez-vous été en arrêt maladie ?",
    'materniteBloc': "Avez-vous été en congé maternité ?",
    'retraiteBloc': "Percevez-vous une nouvelle pension retraite ?",
    'invaliditeBloc': "Percevez-vous une nouvelle pensiond'invalidité de 2ème ou 3ème catégorie ?",
    'rechercheBloc': "Etes-vous toujours à la recherche d'un emploi ?"
}

default_answers = {
    'travailleBloc': "NON",
    'stageBloc': "NON",
    'maladieBloc': "NON",
    'materniteBloc': "NON",
    'retraiteBloc': "NON",
    'invaliditeBloc': "NON",
    'rechercheBloc': "OUI"
}



smtphost = None
smtpport = None
smtpaccount = None
smtppassword = None



def sendmail(to, subj, msg, attachments=[]):
    # FIXME: use email.policy.SMTP when the bug #34424 is fixed
    policy = email.policy.EmailPolicy(raise_on_defect=True, linesep="\r\n", utf8=True)
    mail = email.message.EmailMessage(policy=policy)
    mail['Subject'] = "[BOT Paul Emploi] %s" % subj
    mail['From'] = "%s <%s>" % ("Auto-actualisation", smtpaccount)
    mail['To'] = "Chômeur <%s>" % to
    mail.set_content(msg, disposition='inline')

    for name, content in attachments:
        mime, encoding = mimetypes.guess_type(name)
        if mime is None or encoding is not None:
            mime = "application/octet-stream"

        maintype, subtype = mime.split("/")
        mail.add_attachment(content, maintype=maintype, subtype=subtype, filename=name)

    smtp = smtplib.SMTP_SSL(smtphost, port=smtpport)
    smtp.login(smtpaccount, smtppassword)
    smtp.send_message(mail)
    smtp.quit()



def extract_peam(script):
    match = re.search(r'peam:({(?:[^{}]*\{[^{}]*\})*})', script)
    peam = match.group(1)
    peam = re.sub(r'(?<=[{,])([a-zA-Z0-9_]+)(?=:)', '"\\1"', peam)
    peam = json.loads(peam)
    return peam



def extract_rest(script):
    match = re.search(r'rest:({(?:[^{}]*\{[^{}]*\})*})', script)
    rest = match.group(1)
    rest = re.sub(r'(?<=[{,])([a-zA-Z0-9_]+)(?=:)', '"\\1"', rest)
    rest = json.loads(rest)
    return rest



def randomizeString(n):
    charset = "0123456789ABCDEFGHIJKLMNOPQRSTUVXYZabcdefghijklmnopqrstuvwxyz-"
    return "".join(random.choices(charset, k=n))



def buildAuthorizeUrl(peam):
    openAMUrl = peam['openAMUrl']
    redirectUri = peam['redirectUri']
    realm = peam['commonRessource']['realm']
    clientId = peam['commonRessource']['clientId']
    url = peam['authorizeResource']['url']
    scope = peam['authorizeResource']['scope']
    responseType = peam['authorizeResource']['responseType']

    authorization_endpoint = openAMUrl + url
    state = randomizeString(16)
    nonce = randomizeString(16)

    params = {
        'realm': realm,
        'response_type': responseType,
        'scope': scope,
        'client_id': clientId,
        'state': state,
        'nonce': nonce,
        'redirect_uri': redirectUri,
        #'prompt': 'none'
    }

    params = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return authorization_endpoint + '?' + params



class PaulEmploiAuthedRequests(object):
    def __init__(self, user, password):
        self._session = requests.Session()
        self._session.headers.update({'User-Agent': 'Mozzarella/5.0'})
        self._rest = None
        self._access_token = None
        self._login(user, password)



    def request(self, method, url, *args, **kwargs):
        res = self._session.request(method, url, *args, **kwargs)
        res.raise_for_status()
        return res

    def get(self, url, *args, **kwargs):
        res = self._session.get(url, *args, **kwargs)
        res.raise_for_status()
        return res

    def post(self, url, *args, **kwargs):
        res = self._session.post(url, *args, **kwargs)
        res.raise_for_status()
        return res



    def _authorizeUrl(self):
        initialurl = "https://candidat.pole-emploi.fr/espacepersonnel/"
        res = self.get(initialurl)

        doc = lxml.html.fromstring(res.text, base_url=res.url)
        doc.make_links_absolute()

        # Find and load main.*.js script to extract some informations from it
        mainscripts = doc.cssselect('script[src*="/main."][src$=".js"]')
        if len(mainscripts) == 0:
            raise ValueError("No main.js script found")
        if len(mainscripts) > 1:
            raise ValueError("Several main.js scripts were found")

        mainscript = mainscripts[0].get('src')
        res = self.get(mainscript)

        mainjs = res.text
        peam = extract_peam(mainjs)
        self._rest = extract_rest(mainjs)
        return buildAuthorizeUrl(peam)



    @staticmethod
    def _realm_override(url):
        # TODO: cache the result?
        qs = urllib.parse.parse_qs(url.fragment)
        if 'realm' not in qs:
            qs = urllib.parse.parse_qs(url.query)
        realm = qs['realm'][-1]
        return realm



    @staticmethod
    def _realm_path(realm):
        if realm[0] == "/":
            realm = "/root" + realm
        realm = realm.replace("/", "/realms/")
        return realm



    @staticmethod
    def _pathjson(url):
        # TODO: cache the result?
        pathcontext = "/".join(url.path.rstrip('/').split("/")[:-1])
        pathjson = pathcontext + "/json"
        return pathjson



    def _cookiedesc_tokenid(self, url):
        realm = self._realm_override(url)
        pathjson = self._pathjson(url)

        path = pathjson + "/serverinfo/*"
        params = {'realm': realm}
        params = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        configurl = urllib.parse.urlunsplit((url.scheme, url.netloc, path, params, None))

        res = self.get(configurl)
        srvinfo = res.json()

        cookiedesc = {
            "name": srvinfo["cookieName"],
            "domains": srvinfo["domains"],
            "secure": srvinfo["secureCookie"]
        }

        return cookiedesc



    def _authenticate(self, url, user, password):
        realm = self._realm_override(url)
        realmpath = self._realm_path(realm)
        pathjson = self._pathjson(url)

        path = pathjson + realmpath + "/authenticate"
        params = dict(urllib.parse.parse_qsl(url.query))
        params['realm'] = realm # override realm even if we know it's actually the same
        params = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        authurl = urllib.parse.urlunsplit((url.scheme, url.netloc, path, params, None))

        headers = {
            "Accept-API-Version": "protocol=1.0,resource=2.0",
            "X-Password": "anonymous",
            "X-Username": "anonymous",
            "X-NoSession": "true",
            "Content-Type": "application/json",
        }
        res = self.post(authurl, headers=headers)
        form = res.json()

        form['callbacks'][0]['input'][0]['value'] = user
        res = self.post(authurl, data=json.dumps(form), headers=headers)
        form = res.json()

        form['callbacks'][1]['input'][0]['value'] = password

        res = self.post(authurl, data=json.dumps(form), headers=headers)
        return res.json()



    def _login(self, user, password):
        authorizeurl = self._authorizeUrl()
        res = self.get(authorizeurl)
        url = urllib.parse.urlparse(res.url)

        # Keep the cookie description for later
        cookiedesc = self._cookiedesc_tokenid(url)

        # Authenticate
        res = self._authenticate(url, user, password)
        successurl = res['successUrl']

        # Set the tokenId cookie
        cookie = {
            'name': cookiedesc['name'],
            'value': res['tokenId'],
            'secure': cookiedesc['secure']
        }

        for dom in cookiedesc['domains']:
            cookie['domain'] = dom
            self._session.cookies.set(**cookie)

        res = self.get(successurl)

        # Set the access token
        url = urllib.parse.urlparse(res.url)
        qs = urllib.parse.parse_qs(url.fragment)
        self._access_token = qs['access_token'][-1]



    def getSituationsUtilisateur(self):
        headers = {
            "Accept": "application/json, text/plain, */*",
            "pe-nom-application": "pn073-tdbcandidat",
            "Authorization": "Bearer " + self._access_token
        }

        res = self.get(self._rest['ex002']['situationsUtilisateur'], headers=headers)
        return res.json()



class PaulEmploi(object):
    def __init__(self, user, password):
        self._req = PaulEmploiAuthedRequests(user, password)
        self.situationsUtilisateur = self._req.getSituationsUtilisateur()



    def _fill_block(self, bloc, answers):
        blocid = bloc.get('id')
        logging.debug("Filling block %s", blocid)

        # Check that the question hasn't changed
        qs = bloc.cssselect('.label > .list-title')
        if len(qs) == 0:
            qs = bloc.cssselect(".label > label")
        assert len(qs) == 1, "Several questions for a block"
        q = qs[0]
        q = lxml.html.tostring(qs[0], method='text', encoding='unicode')
        matches = re.match(r'^\s*(.*?)\s*(?:Aide\s*)?$', q, re.MULTILINE)
        q = matches.group(1)
        logging.debug("Answering question %r", q)

        if blocid not in questions:
            blocstr = lxml.html.tostring(bloc, encoding='unicode')
            raise ValueError("Unknown question block: %s" % blocstr)

        if questions[blocid] != q:
            raise ValueError("Question changed for block '%s'. Expected %r found %r" % (blocid, questions[blocid], q))

        inputs = bloc.cssselect("input")
        inputnames = set(i.name for i in inputs)
        if len(inputnames) == 0:
            blocstr = lxml.html.tostring(bloc, encoding='unicode')
            raise ValueError("No input in block '%s'\nPlease check the form yourself:\n%s" % (blocid, blocstr))

        if len(inputnames) > 1:
            blocstr = lxml.html.tostring(bloc, encoding='unicode')
            raise ValueError("Several inputs for question %r\nPlease check the form yourself:\n%s" % (q, blocstr))

        inputtype = inputs[0].type.lower()

        if inputtype not in ("text", "radio"):
            raise ValueError("Found an input with type %r. Those aren't supported yet." % inputtype)

        if inputtype == "text":
            return inputs[0].name, answers[blocid], None

        # Check that our answer doesn't show a new question
        inputs = bloc.cssselect('input[value=%s]' % answers[blocid])
        if len(inputs) == 0:
            inputs = bloc.cssselect('input')
            values = [i.value for i in inputs]
            blocstr = lxml.html.tostring(bloc, encoding='unicode')
            raise ValueError("No input for question %r with value %r. Possible values are %r\nPlease check the form yourself:\n%s" % (q, answers[blocid], values, blocstr))

        if len(inputs) > 1:
            blocstr = lxml.html.tostring(bloc, encoding='unicode')
            raise ValueError("Several inputs for question %r with value %r.\nPlease check the form yourself:\n%s" % (q, answers[blocid], blocstr))

        input_ = inputs[0]
        openid = None
        if "js-open" in input_.classes:
            inputid = input_.get('id')
            if inputid.endswith("-open"):
                openid = inputid[:-len("-open")]
                logging.debug("Answering %r to question %r opens block %r.", answers[blocid], q, openid)

        return input_.name, answers[blocid], openid




    def actualisation(self, answers):
        situation = self.situationsUtilisateur

        res = self._req.get(situation['actualisation']['service']['url'])
        doc = lxml.html.fromstring(res.text, base_url=res.url)
        doc.make_links_absolute()

        form = doc.cssselect('form')[0]
        res = self._req.request(form.method, form.action, data=dict(form.fields))
        doc = lxml.html.fromstring(res.text, base_url=res.url)
        doc.make_links_absolute()
        docstr = lxml.html.tostring(doc, method='text', encoding='unicode')

        # During dev, we might redo the "actualisation" thing
        if "Vous avez déjà déclaré votre situation pour cette période" in docstr:
            forms = doc.cssselect('form[action*=actualisation]')
            if len(forms) == 0:
                raise ValueError("Actualisation déjà effectuée et non-modifiable")

            assert len(forms) == 1, "Several forms for re-actualisation"
            form = forms[0]

            values = dict(form.fields)
            res = self._req.request(form.method, form.action, data=values)
            doc = lxml.html.fromstring(res.text, base_url=res.url)
            doc.make_links_absolute()


        forms = doc.cssselect('form[action*=actualisation]')
        assert len(forms) == 1, "Several forms for actualisation"
        form = forms[0]

        fieldsets = form.cssselect('fieldset')
        assert len(fieldsets) == 1

        values = dict(form.fields)
        values['formation'] = "NON"
        res = self._req.request(form.method, form.action, data=values)
        doc = lxml.html.fromstring(res.text, base_url=res.url)
        doc.make_links_absolute()

        forms = doc.cssselect('form[action*=actualisation]')
        assert len(forms) == 1, "Several forms for actualisation"
        form = forms[0]

        formvalues = dict(form.fields)
        blocs = form.cssselect("div:not(.hide) > fieldset:not([id]) > div.form-line:not(.js-hide)")
        for bloc in blocs:
            name, value, showid = self._fill_block(bloc, answers)
            formvalues[name] = value

            if showid is not None:
                blocshow = form.cssselect("#" + showid)
                if len(blocshow) == 0:
                    raise ValueError("Block '%s' should be shown but doesn't exist" % showid)

                blocshow = blocshow[0]
                newblocs = blocshow.cssselect("div.form-line")
                for b in newblocs:
                    name, value, n = self._fill_block(b, answers)
                    formvalues[name] = value
                    if n is not None:
                        raise ValueError("Question block '%s' opened block '%s' which should open a second third level block '%r'. Only 2 levels supported right now." % (bloc.get("id"), showid, n))

        res = self._req.request(form.method, form.action, data=formvalues)
        doc = lxml.html.fromstring(res.text, base_url=res.url)
        doc.make_links_absolute()

        # Extract summary
        (formresult,) = doc.cssselect('.form-result')
        header = formresult.getprevious()
        msg = lxml.html.tostring(header, method='text', encoding='unicode').strip()
        msg += "\n"
        lis = formresult.cssselect('ul > li')
        for li in lis:
            msg += lxml.html.tostring(li, method='text', encoding='unicode').strip()
            msg += "\n"

        # Confirm that it's all good
        forms = doc.cssselect('form[action*=actualisation]')
        assert len(forms) == 1, "Several forms for actualisation"
        form = forms[0]

        values = dict(form.fields)
        res = self._req.request(form.method, form.action, data=values)
        doc = lxml.html.fromstring(res.text, base_url=res.url)
        doc.make_links_absolute()

        links = doc.cssselect('#link-redirect > a')
        assert len(links) == 1, "Several links to last page"
        link = links[0]

        res = self._req.get(link.get('href'))
        doc = lxml.html.fromstring(res.text, base_url=res.url)
        doc.make_links_absolute()

        pdflinks = doc.cssselect('.pdf-fat-link')
        assert len(pdflinks) == 1
        pdflink = pdflinks[0]

        res = self._req.get(pdflink.get('href'))
        pdf = res.content

        return msg, pdf



def make_answers(datestart, workfile=None):
    answers = default_answers.copy()
    if workfile is None:
        logging.debug("No work file to parse")
        return answers

    datestart = datestart.date().replace(day=1)
    _, daysinmonth = calendar.monthrange(datestart.year, datestart.month)
    dateend = datestart + datetime.timedelta(days=daysinmonth)
    logging.info("Looking for work entries between %s and %s", datestart, dateend)

    parsere = re.compile(r'(\S+)\s+(\S+)\s+(\S+)')

    totalhours = 0
    totalrevenue = 0
    logging.info("Reading workfile: %s", workfile)

    with open(workfile) as fp:
        for line in fp:
            logging.debug("Reading workfile line: %r", line)
            line = line.split("#", 1)[0].rstrip()
            if not line:
                logging.debug("Ignoring empty line")
                continue

            match = parsere.match(line)
            if match is None:
                raise ValueError("Ill-formatted line in workfile: %r" % line)

            date = match.group(1)
            hours = match.group(2)
            rate = match.group(3)

            date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
            if date < datestart or date >= dateend:
                logging.debug("Date %s not in interval %s ... %s", date, datestart, dateend)
                continue

            hours = float(hours)
            rate = float(rate)
            revenue = hours * rate
            logging.debug("Adding %f hours and %f€ to the count", hours, revenue)

            totalhours += hours
            totalrevenue += revenue
            logging.debug("New total of %f hours and %f€", totalhours, totalrevenue)


    totalhours = int(totalhours)
    totalrevenue = int(totalrevenue)

    if totalhours == 0 and totalrevenue == 0:
        logging.debug("Work file show nothing for this month")
        return answers

    logging.info("Declaring %d hours for %d€", totalhours, totalrevenue)
    answers["travailleBloc"] = "OUI"
    answers["nbHeuresTravBloc"] = totalhours
    answers["montSalaireBloc"] = totalrevenue

    return answers



def dostuff(dest, user, password, workfile=None):
    pe = PaulEmploi(user, password)

    situation = pe.situationsUtilisateur
    indemnisation = situation['indemnisation']
    actualisation = situation['actualisation']
    enddate = datetime.datetime.fromisoformat(indemnisation['dateDecheanceDroitAre'])
    indemndate = datetime.datetime.fromisoformat(actualisation['periodeCourante']['reference'])
    answers = make_answers(indemndate, workfile)
    actumsg, pdf = pe.actualisation(answers)

    dailyindemn = float(indemnisation['indemnisationJournalierNet'])
    _, daysinmonth = calendar.monthrange(indemndate.year, indemndate.month)
    indemnestimate = dailyindemn * daysinmonth

    msg = actumsg + "\n"
    msg += "Indemnisation prévue pour le mois de %s: %.2f€\n" % (indemndate.strftime("%B"), indemnestimate)
    msg += "Droit au chômage jusqu'au: %s\n" % enddate.strftime("%x")

    jsondump = json.dumps(situation, indent=8).encode("utf-8")
    att = [("situation.json", jsondump), ("declaration.pdf", pdf)]

    sendmail(dest, "Actualisation", msg, att)



def main():
    locale.setlocale(locale.LC_ALL, '')
    logfmt = "%(asctime)s %(levelname)s: %(message)s"
    logging.basicConfig(format=logfmt, level=logging.WARNING)

    parser = argparse.ArgumentParser(description="Bot d'actualisation pour Paul Emploi")
    parser.add_argument("cfgfile", metavar="configfile", help="Fichier de configuration")
    parser.add_argument("--user", "-u", metavar="PEusername", help="Compte Pôle Emploi configuré à utiliser")
    parser.add_argument("--work", "-w", metavar="worklog", help="Fichier des heures travaillées")
    parser.add_argument("--verbose", "-v", action="count", help="Augmente le niveau de verbosité")

    args = parser.parse_args()

    configpath = args.cfgfile
    peuser = args.user
    verbose = args.verbose
    workfile = args.work

    if verbose is not None:
        loglevels = ["WARNING", "INFO", "DEBUG", "NOTSET"]
        verbose = min(len(loglevels), verbose) - 1
        logging.getLogger().setLevel(loglevels[verbose])

    logging.info("Reading config file %s", configpath)
    config = configparser.ConfigParser()
    config.read(configpath)

    global smtphost, smtpport, smtpaccount, smtppassword
    smtphost = config["SMTP"]["smtphost"]
    smtpport = config["SMTP"].get("smtpport")
    smtpaccount = config["SMTP"]["smtpuser"]
    smtppassword = config["SMTP"]["smtppwd"]


    if peuser is None:
        section = next(s for s in config.sections() if s.startswith("Account."))
    else:
        section = "Account." + peuser

    logging.info("Using account section %s", section)
    peuser = config[section]["username"]
    pepwd = config[section]["password"]
    emailaddr = config[section]["email"]

    try:
        dostuff(emailaddr, peuser, pepwd, workfile)
    except:
        logging.exception("Top-level exception:")
        msg = "Exception caught while trying to run the \"actualisation\".\n\n"
        msg += traceback.format_exc()
        sendmail(smtpaccount, "Error", msg)





if __name__ == '__main__':
    main()
