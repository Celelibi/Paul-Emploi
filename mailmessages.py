#!/usr/bin/env python3

import argparse
import configparser
import locale
import logging
import traceback
import unicodedata

import mailer
import paul



def dostuff(mailsender, dest, user, password, allmessages, since, nosend):
    pe = paul.PaulEmploi(user, password)
    maildesc = pe.newmails(allmessages, since)

    if nosend:
        print(len(maildesc), "messages to send")
    else:
        logging.info("%d messages to send by email", len(maildesc))

    maildesc.sort(key=lambda m: m['date'])

    for m in maildesc:
        msg = "Date: %s\n" % m['date'].strftime("%d/%m/%Y")
        msg += "Titre: %s\n" % m['title']

        filename = m['title'].lower().replace(" ", "_") + ".pdf"
        filename = unicodedata.normalize("NFD", filename)
        filename = filename.encode("ascii", "ignore").decode("utf-8")

        if nosend:
            print(m['date'], m['title'], filename)
        else:
            pdf = pe.download_mail(m['link'])
            att = [(filename, pdf)]
            mailsender.message(dest, m['title'], msg, att)



def main():
    locale.setlocale(locale.LC_ALL, '')
    logfmt = "%(asctime)s %(levelname)s: %(message)s"
    logging.basicConfig(format=logfmt, level=logging.WARNING)

    parser = argparse.ArgumentParser(description="Bot d'actualisation pour Paul Emploi")
    parser.add_argument("cfgfile", metavar="configfile", help="Fichier de configuration")
    parser.add_argument("--user", "-u", metavar="PEusername", help="Compte Pôle Emploi configuré à utiliser")
    parser.add_argument("--all", action='store_true', help="Envoie tous les messages et pas seulement ceux non-lus")
    parser.add_argument("--since", metavar="JJ/MM/AAAA", help="Envoie uniquement les messages reçus après cette date")
    parser.add_argument("--no-send", "-n", action='store_true', help="N'envoie pas les mails, affiche le résumé")
    parser.add_argument("--verbose", "-v", action="count", help="Augmente le niveau de verbosité")

    args = parser.parse_args()

    configpath = args.cfgfile
    peuser = args.user
    verbose = args.verbose
    allmessages = args.all
    since = args.since
    nosend = args.no_send

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
        dostuff(mailsender, emailaddr, peuser, pepwd, allmessages, since, nosend)
    except KeyboardInterrupt:
        raise
    except:
        logging.exception("Top-level exception:")
        msg = "Exception caught while trying to run \"mailmessages\".\n\n"
        msg += traceback.format_exc()
        mailsender.error(smtpuser, msg)





if __name__ == '__main__':
    main()
