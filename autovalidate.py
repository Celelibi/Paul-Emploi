#!/usr/bin/env python3

import calendar
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
import sys
import traceback
import urllib.parse

import lxml.html
import requests



gmailaccount = None
gmailpassword = None


def sendmail(to, subj, msg, attachments=[]):
    # FIXME: use email.policy.SMTP when the bug #34424 is fixed
    policy = email.policy.EmailPolicy(raise_on_defect=True, linesep="\r\n", utf8=True)
    mail = email.message.EmailMessage(policy=policy)
    mail['Subject'] = "[BOT Paul Emploi] %s" % subj
    mail['From'] = "%s <%s>" % ("Auto-actualisation", gmailaccount)
    mail['To'] = "Chômeur <%s>" % to
    mail.set_content(msg, disposition='inline')

    for name, content in attachments:
        mime, encoding = mimetypes.guess_type(name)
        if mime is None or encoding is not None:
            mime = "application/octet-stream"

        maintype, subtype = mime.split("/")
        mail.add_attachment(content, maintype=maintype, subtype=subtype, filename=name)

    smtp = smtplib.SMTP_SSL("smtp.gmail.com")
    smtp.login(gmailaccount, gmailpassword)
    smtp.send_message(mail)
    smtp.quit()



class MySession(requests.Session):
    def _common(self, req):
        req = self.prepare_request(req)

        print("%s %s" % (req.method, req.url))
        for header in req.headers.items():
            print("%s: %s" % header)

        print("")

        res = self.send(req)

        def print_response(res):
            print("%s %s" % (res.status_code, res.reason))
            for h in res.headers.items():
                print("%s: %s" % h)

            print("")

        for h in res.history:
            print_response(h)
        print_response(res)
        return res

    def get(self, *args, **kwargs):
        req = requests.Request("GET", *args, **kwargs)
        return self._common(req)

    def post(self, *args, **kwargs):
        req = requests.Request("POST", *args, **kwargs)
        return self._common(req)

    def request(self, method, *args, **kwargs):
        req = requests.Request(method, *args, **kwargs)
        return self._common(req)



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



class PaulEmploi(object):
    def __init__(self, user, password):
        self._session = requests.Session()
        self._session.headers.update({'User-Agent': 'Mozzarella/5.0'})
        self._peam = None
        self._rest = None
        self._access_token = None
        self._situation = None
        self._login(user, password)



    def _authorizeUrl(self):
        initialurl = "https://candidat.pole-emploi.fr/espacepersonnel/"
        res = self._session.get(initialurl)
        res.raise_for_status()

        doc = lxml.html.fromstring(res.text, base_url=res.url)
        doc.make_links_absolute()

        # Find and load main.*.js script to extract some informations from it
        mainscripts = doc.cssselect('script[src*="/main."][src$=".js"]')
        if len(mainscripts) == 0:
            raise ValueError("No main.js script found")
        if len(mainscripts) > 1:
            raise ValueError("Several main.js scripts were found")

        mainscript = mainscripts[0].get('src')
        res = self._session.get(mainscript)
        res.raise_for_status()

        mainjs = res.text
        self._peam = extract_peam(mainjs)
        self._rest = extract_rest(mainjs)
        return buildAuthorizeUrl(self._peam)



    @staticmethod
    def _realm_override(url):
        # TODO: cache the result?
        qs = urllib.parse.parse_qs(url.fragment)
        realm = qs['realm'][-1]
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

        res = self._session.get(configurl)
        res.raise_for_status()
        srvinfo = res.json()

        cookiedesc = {
            "name": srvinfo["cookieName"],
            "domains": srvinfo["domains"],
            "secure": srvinfo["secureCookie"]
        }

        return cookiedesc



    def _authenticate(self, url, user, password):
        realm = self._realm_override(url)
        pathjson = self._pathjson(url)

        path = pathjson + "/authenticate"
        params = dict(urllib.parse.parse_qsl(url.fragment))
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
        res = self._session.post(authurl, headers=headers)
        res.raise_for_status()
        form = res.json()

        form['callbacks'][0]['input'][0]['value'] = user
        res = self._session.post(authurl, data=json.dumps(form), headers=headers)
        res.raise_for_status()
        form = res.json()

        form['callbacks'][1]['input'][0]['value'] = password

        res = self._session.post(authurl, data=json.dumps(form), headers=headers)
        res.raise_for_status()
        return res.json()



    def _login(self, user, password):
        authorizeurl = self._authorizeUrl()
        res = self._session.get(authorizeurl)
        res.raise_for_status()

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

        res = self._session.get(successurl)
        res.raise_for_status()

        # Set the access token
        url = urllib.parse.urlparse(res.url)
        qs = urllib.parse.parse_qs(url.fragment)
        self._access_token = qs['access_token'][-1]



    @property
    def situationsUtilisateur(self):
        if self._situation is not None:
            return self._situation

        headers = {
            "Accept": "application/json, text/plain, */*",
            "pe-nom-application": "pn073-tdbcandidat",
            "Authorization": "Bearer " + self._access_token
        }

        res = self._session.get(self._rest['ex002']['situationsUtilisateur'], headers=headers)
        res.raise_for_status()
        self._situation = res.json()
        return self._situation



    def actualisation(self):
        situation = self.situationsUtilisateur

        res = self._session.get(situation['actualisation']['service']['url'])
        res.raise_for_status()

        doc = lxml.html.fromstring(res.text, base_url=res.url)
        doc.make_links_absolute()

        form = doc.cssselect('form')[0]
        res = self._session.request(form.method, form.action, data=dict(form.fields))
        res.raise_for_status()

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
            res = self._session.request(form.method, form.action, data=values)
            res.raise_for_status()
            doc = lxml.html.fromstring(res.text, base_url=res.url)
            doc.make_links_absolute()


        forms = doc.cssselect('form[action*=actualisation]')
        assert len(forms) == 1, "Several forms for actualisation"
        form = forms[0]

        fieldsets = form.cssselect('fieldset')
        assert len(fieldsets) == 1
        fieldset = fieldsets[0]

        values = dict(form.fields)
        values['formation'] = "NON"
        res = self._session.request(form.method, form.action, data=values)
        res.raise_for_status()

        doc = lxml.html.fromstring(res.text, base_url=res.url)
        doc.make_links_absolute()

        forms = doc.cssselect('form[action*=actualisation]')
        assert len(forms) == 1, "Several forms for actualisation"
        form = forms[0]

        questions = {
            'travailleBloc': "Avez-vous travaillé ou exercé une activité non salariée ?",
            'stageBloc': "Avez-vous été en stage ?",
            'maladieBloc': "Avez-vous été en arrêt maladie ?",
            'materniteBloc': "Avez-vous été en congé maternité ?",
            'retraiteBloc': "Percevez-vous une nouvelle pension retraite ?",
            'invaliditeBloc': "Percevez-vous une nouvelle pensiond'invalidité de 2ème ou 3ème catégorie ?",
            'rechercheBloc': "Etes-vous toujours à la recherche d'un emploi ?"
        }

        answers = {
            'travailleBloc': "NON",
            'stageBloc': "NON",
            'maladieBloc': "NON",
            'materniteBloc': "NON",
            'retraiteBloc': "NON",
            'invaliditeBloc': "NON",
            'rechercheBloc': "OUI"
        }

        formvalues = dict(form.fields)
        blocs = form.cssselect('fieldset:not([id]) > div:not(.js-hide)')
        for bloc in blocs:
            blocid = bloc.get('id')

            # Check that the question hasn't changed
            qs = bloc.cssselect('.label > .list-title')
            assert len(qs) == 1, "Several questions for a block"
            q = qs[0]
            q = lxml.html.tostring(qs[0], method='text', encoding='unicode')
            matches = re.match(r'^\s*(.*?)\s*(?:Aide\s*)?$', q, re.MULTILINE)
            q = matches.group(1)

            if blocid not in questions:
                blocstr = lxml.html.tostring(bloc, encoding='unicode')
                raise ValueError("Unknown question block: %s" % blocstr)

            if questions[blocid] != q:
                raise ValueError("Question changed for block '%s'. Expected %r found %r" % (blocid, questions[blocid], q))


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
            if "js-open" in input_.classes:
                # TODO if this is needed, parse the question tree
                raise ValueError("Answering %r to question %r would open new questions. This case is not handled right now." % (answers[blocid], q))

            formvalues[input_.name] = answers[blocid]

        res = self._session.request(form.method, form.action, data=formvalues)
        res.raise_for_status()

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
        res = self._session.request(form.method, form.action, data=values)
        res.raise_for_status()

        doc = lxml.html.fromstring(res.text, base_url=res.url)
        doc.make_links_absolute()

        links = doc.cssselect('#link-redirect > a')
        assert len(links) == 1, "Several links to last page"
        link = links[0]

        res = self._session.get(link.get('href'))
        res.raise_for_status()

        doc = lxml.html.fromstring(res.text, base_url=res.url)
        doc.make_links_absolute()

        pdflinks = doc.cssselect('.pdf-fat-link')
        assert len(pdflinks) == 1
        pdflink = pdflinks[0]

        res = self._session.get(pdflink.get('href'))
        res.raise_for_status()
        pdf = res.content

        return msg, pdf



def dostuff(dest, user, password):
    pe = PaulEmploi(user, password)

    situation = pe.situationsUtilisateur
    indemnisation = situation['indemnisation']
    actualisation = situation['actualisation']
    actumsg, pdf = pe.actualisation()

    enddate = datetime.datetime.fromisoformat(indemnisation['dateDecheanceDroitAre'])
    indemndate = datetime.datetime.fromisoformat(actualisation['periodeCourante']['reference'])
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
    logging.basicConfig(format=logfmt, level=logging.INFO)

    if len(sys.argv) != 6:
        print("usage: %s gmailaccount gmailpassword destinationmail username password" % sys.argv[0])
        return

    global gmailaccount, gmailpassword
    gmailaccount = sys.argv[1]
    gmailpassword = sys.argv[2]

    try:
        dostuff(*sys.argv[3:])
    except:
        msg = "Exception caught while trying to run the \"actualisation\".\n\n"
        msg += traceback.format_exc()
        sendmail(gmailaccount, "Error", msg)





if __name__ == '__main__':
    main()
