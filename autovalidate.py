#!/usr/bin/env python3

import argparse
import calendar
import configparser
import datetime
import json
import locale
import logging
import re
import traceback

import mailer
import paul



def make_answers(datestart, workfile=None):
    answers = paul.default_answers.copy()
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



def msgindemn(indemn, date):
    if "typeAllocation" not in indemn:
        return "Pas d'allocation prévue"

    if indemn['typeAllocation'] != "ARE":
        return "Allocation de type %r, pas de détails" % indemn['typeAllocation']

    dailyindemn = float(indemn['indemnisationJournalierNet'])
    _, daysinmonth = calendar.monthrange(date.year, date.month)
    indemnestimate = dailyindemn * daysinmonth

    enddate = datetime.datetime.fromisoformat(indemn['dateDecheanceDroitAre'])

    msg = "Indemnisation prévue pour le mois de %s: %.2f€\n" % (date.strftime("%B"), indemnestimate)
    msg += "Droit au chômage jusqu'au: %s\n" % enddate.strftime("%x")
    return msg



def dostuff(mailsender, dest, user, password, workfile=None):
    pe = paul.PaulEmploi(user, password)

    situation = pe.getSituationsUtilisateur()
    indemnisation = situation['indemnisation']
    actualisation = situation['actualisation']

    if 'periodeCourante' not in actualisation:
        raise RuntimeError("Looks like it's not the time for an 'actulisation'")

    indemndate = datetime.datetime.fromisoformat(actualisation['periodeCourante']['reference'])
    answers = make_answers(indemndate, workfile)
    actumsg, pdf = pe.actualisation(answers)

    msg = actumsg + "\n" + msgindemn(indemnisation, indemndate)

    jsondump = json.dumps(situation, indent=8).encode("utf-8")
    att = [("situation.json", jsondump), ("declaration.pdf", pdf)]

    mailsender.message(dest, "Actualisation", msg, att)



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

    smtphost = config["SMTP"]["smtphost"]
    smtpport = config["SMTP"].get("smtpport")
    smtpuser = config["SMTP"].get("smtpuser")
    smtppassword = config["SMTP"].get("smtppwd")
    mailsender = mailer.Mailer(smtphost, smtpport, smtpuser, smtppassword)


    if peuser is None:
        section = next(s for s in config.sections() if s.startswith("Account."))
    else:
        section = "Account." + peuser

    logging.info("Using account section %s", section)
    peuser = config[section]["username"]
    pepwd = config[section]["password"]
    emailaddr = config[section]["email"]

    try:
        dostuff(mailsender, emailaddr, peuser, pepwd, workfile)
    except:
        logging.exception("Top-level exception:")
        msg = "Exception caught while trying to run the \"actualisation\".\n\n"
        msg += traceback.format_exc()
        mailsender.error(smtpuser, msg)





if __name__ == '__main__':
    main()
