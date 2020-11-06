# Bot d'actualisation de situation Pôle Emploi

Ce programme rempli automatiquement le formulaire d'actualisation sur le site
de Paul. Pour l'instant, il remplit le formulaire toujours de la même façon en
répondant "Oui" à "Etes-vous toujours à la recherche d'un emploi ?" et "Non" à
toutes les autres.

En cas de succès il envoie un mail à l'adresse indiquée avec un résumé de
l'actualisation. En cas d'échec, il envoie un rapport d'erreur au compte mail
utilisé pour l'envoi des mails. L'envoie de mails a été testé uniquement avec
un compte gmail.

# Utilisation

L'utilisation prévue est de lancer le bot tous les mois avec une entrée cron
telle que suit:

    0 8 1 * * dir/to/autovalidate.py dir/to/autovalidate.ini cfgUser

Le premier argument est le chemin vers le fichier de configuration dont la
syntaxe est détaillée plus loin.

`cfgUser` est le nom du compte utilisateur défini dans la configuration pour
qui il faut effectuer l'actualisation sur le site Pôle Emploi.

# Fichier de configuration

Le fichier de configuration suit la syntaxe des fichiers INI et ressemble à
ceci.

```ini
[SMTP]
smtphost = smtp.gmail.com
#smtpport = 465
smtpuser = youraccount@gmail.com
smtppwd = GMa1lP4s5W0rD

[Account.PEusername]
username = loginPE
password = p4ssw0rdPE
email = something@example.com
```

La section `SMTP` décrit le serveur SMTP à utiliser pour envoyer des mails.
Ensuite, les sections commençant par `Account.` définissent les comptes
utilisateur configurés.

## La section [SMTP]
- `smtphost` et `smtpport` définissent le nom de domaine et le port du serveur
  SMTP. Note: Il s'agit nécessairement du port SMTPS et le port par défaut est
  465.
- `smtpuser` et `smtppwd` définissent le login et le mot de passe nécessaire
  pour se connecter au serveur SMTP.

## La section [Account.PEusername]
Le `PEusername` dans le nom de la section est modifiable. C'est le nom qui doit
être donné sur la ligne de commande.

- `username` et `password` définissent le nom d'utilisateur et le mot de passe
  de connexion sur le site de Pôle Emploi tel que mis en place depuis l'été 2019.
- `email` définit l'adresse mail où envoyer le résumé si l'actualisation
  réussit.

# Améliorations possibles

- Tester le support d'autres serveurs mail que GMail pour l'envoi.
- Support d'autres cas de remplissage du formulaire, notamment pour les
  auto-entepreneurs.

Contributions welcome.
