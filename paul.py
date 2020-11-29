import datetime
import json
import logging
import random
import re
import urllib.parse

import lxml.html
import requests


__all__ = ['PaulEmploi', 'PaulEmploiAuthedRequests', 'default_answers']



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



def extract_layout(script):
    start = script.index("layout:") + len("layout:")
    nextopen = script.find("{", start)
    pos = nextopen + 1
    nextopen = script.find("{", pos)
    nextclose = script.find("}", pos)
    count = 1

    while count > 0:
        assert nextclose != -1
        if nextopen != -1 and nextopen < nextclose:
            pos = nextopen + 1
            count += 1
            nextopen = script.find("{", pos)
        else:
            pos = nextclose + 1
            count -= 1
            nextclose = script.find("}", pos)

    layout = script[start:pos]
    layout = re.sub(r'(?<=[{,])([a-zA-Z0-9_]+)(?=:)', '"\\1"', layout)
    return json.loads(layout)



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
        self._layout = None
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

    def getjson(self, url):
        headers = {
            "Accept": "application/json, text/plain, */*",
            "pe-nom-application": "pn073-tdbcandidat",
            "Authorization": "Bearer " + self._access_token
        }

        res = self.get(url, headers=headers)
        return res.json()



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
        self._layout = extract_layout(mainjs)
        return buildAuthorizeUrl(peam)



    @staticmethod
    def _realm_override(url):
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
        return self.getjson(self._rest['ex002']['situationsUtilisateur'])



    def getNavigation(self):
        d = self._layout['rest']['ex017']
        return self.getjson(d['uri'] + d['navigation'])



class PaulEmploi(object):
    def __init__(self, user, password):
        self._req = PaulEmploiAuthedRequests(user, password)
        self._situationsUtilisateur = None
        self._navigation = None



    def getSituationsUtilisateur(self, force=False):
        if self._situationsUtilisateur is None or force:
            self._situationsUtilisateur = self._req.getSituationsUtilisateur()
        return self._situationsUtilisateur



    def getNavigation(self, force=False):
        if self._navigation is None or force:
            self._navigation = self._req.getNavigation()
        return self._navigation



    def navigation_service_url(self, path):
        navigation = self.getNavigation()

        def tree_descent(trees, path):
            code, *path = path
            trees = [t for t in trees if t['code'] == code]
            if len(trees) > 1:
                raise RuntimeError("More than one element with code " + code)
            if len(trees) == 0:
                raise RuntimeError("No element with code " + code)

            if len(path) == 0:
                return trees[0]

            return tree_descent(trees[0]["sousElements"], path)

        path = path.split("/")
        service = tree_descent(navigation['burger'], path)
        return service["url"]



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
        url = self.navigation_service_url("dossier-de/actualisation/m-actualiser")
        res = self._req.get(url)
        doc = lxml.html.fromstring(res.text, base_url=res.url)
        doc.make_links_absolute()

        # One pesky self-submitting form
        form = doc.forms[0]
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



    def _mails_desc(self, pyjama):
        mails = []

        for row in pyjama.cssselect('tr'):
            if row.cssselect('th'):
                continue

            mail = {}
            isread = ("courrierNonLu" not in row.classes)
            mail['isread'] = isread

            date, = row.cssselect('td.date')
            date = date.text_content()
            mail['date'] = datetime.datetime.strptime(date, "%d/%m/%Y").date()

            title, = row.cssselect('td.avisPaie')
            mail['title'] = title.text_content()

            channel, = row.cssselect('td.courrierPap')
            mail['channel'] = channel.text_content()

            link, = row.cssselect('td.Telechar a')
            mail['link'] = link.get('href')

            mails.append(mail)

        return mails



    def _all_mails_desc(self, doc):
        pyjamas = doc.cssselect('table.listingPyjama')
        if len(pyjamas) == 0:
            return []

        paging, = doc.cssselect('.pagination')

        onlydigitsre = re.compile(r'^[0-9]+$')
        pagelinks = []
        for l in paging.cssselect('a'):
            if onlydigitsre.match(l.text_content()):
                href = l.get('href')
                pagelinks.append(href)

        pyjama, = doc.cssselect('table.listingPyjama')
        mails = self._mails_desc(pyjama)

        for link in pagelinks:
            res = self._req.get(link)
            doc = lxml.html.fromstring(res.content, base_url=res.url)
            doc.make_links_absolute()

            pyjama, = doc.cssselect('table.listingPyjama')
            mails += self._mails_desc(pyjama)

        return mails



    def newmails(self, allmessages=False, since=None):
        url = self.navigation_service_url("dossier-de/echanges-avec-pe/courriers-recus-pe")
        res = self._req.get(url)
        doc = lxml.html.fromstring(res.content, base_url=res.url)
        doc.make_links_absolute()

        # Just an annoying auto-validated form
        form = doc.forms[0]
        formvalues = {inp.name: inp.value for inp in form.cssselect('input')}
        res = self._req.request(form.method, form.action, data=formvalues)

        doc = lxml.html.fromstring(res.content, base_url=res.url)
        doc.make_links_absolute()

        # Select all the relevant mails
        form = doc.forms[0]
        inputs = form.cssselect('input[type!="radio"]')
        formvalues = {inp.name: inp.value for inp in inputs}

        if not allmessages:
            # Check the radio input and uncheck all others
            tocheck, = form.cssselect('input#nonlu')
            groupname = tocheck.name
            for inp in form.cssselect('input[name="%s"]' % groupname):
                inp.checked = False

            tocheck.checked = True

        inputs = form.cssselect('input[type="radio"]')
        names = set(inp.name for inp in inputs)
        for n in names:
            group = [inp for inp in inputs if inp.name == n]
            formvalues[n] = next(inp.value for inp in group if inp.checked)

        for sel in form.cssselect('select'):
            formvalues[sel.name] = sel.value

        if since:
            formvalues['dateDebut'] = since

        res = self._req.request(form.method, form.action, data=formvalues)
        doc = lxml.html.fromstring(res.content, base_url=res.url)
        doc.make_links_absolute()

        return self._all_mails_desc(doc)



    def download_mail(self, link):
        res = self._req.get(link)
        doc = lxml.html.fromstring(res.content, base_url=res.url)
        doc.make_links_absolute()

        iframe, = doc.cssselect('iframe')
        res = self._req.get(iframe.get('src'))
        assert res.headers['Content-Type'] == "application/pdf"

        return res.content
