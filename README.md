# Bot d'actualisation de situation Pôle Emploi

Ce programme rempli automatiquement le formulaire d'actualisation sur le site
de Paul. Par défaut, il remplit le formulaire en répondant *"Oui"* à
*"Etes-vous toujours à la recherche d'un emploi ?"* et *"Non"* à toutes les
autres. Cependant, avec l'option `--work`, des heures travaillées peuvent être
déclarées.

En cas de succès il envoie un mail à l'adresse indiquée avec un résumé de
l'actualisation. En cas d'échec, il envoie un rapport d'erreur au compte mail
utilisé pour l'envoi des mails. L'envoie de mails a été testé uniquement avec
un compte gmail.

# Utilisation

L'utilisation prévue est de lancer le bot tous les mois avec une entrée cron
telle que suit:

    0 8 1 * * dir/to/autovalidate.py dir/to/autovalidate.ini --user cfgUser

Le premier argument est le chemin vers le fichier de configuration dont la
syntaxe est détaillée plus loin.

`cfgUser` est le nom du compte utilisateur défini dans la configuration pour
qui il faut effectuer l'actualisation sur le site Pôle Emploi. S'il est omit,
le premier compte définit dans le fichier de configuration sera utilisé.

L'option `--work` peut être utilisée pour donner le chemin d'un fichier
contenant l'historique des heures travaillées. Son format est détaillé plus
loin. S'il est donné et qu'il indique que des heures ont été travaillées pour
la période considérée, alors le script répondra "*Oui"* à la question
*"Avez-vous travaillé ?"* et déclarera le nombre d'heures du mois ainsi que le
chiffre d'affaire estimé.

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

# Work file

Le *work file* liste les heures travaillées ou prévues. Seules les lignes
concernant le mois en cours de déclaration seront utilisées. Plusieurs lignes
peuvent concerner la même journée sans problème. Elles seront cumulées.

## Format

Voici un exemple de *work file*.
```
# Date heures THM
2020-11-02 4 50 # Bad ass stunt
2020-11-02 1 30

2020-11-04 2 40 # Broke my leg like a boss
```

Le fichier peut contenir des commentaires, des lignes vides ou des lignes de
données.  Les lignes de données sont constituées de 3 colonnes, date, heures et
taux horaire. Ces 3 colonnes sont séparées par des caractères blancs (espaces
ou tabulations).

### Commentaires
Tout ce qui se trouve après un symbole `#` est ignoré. Ceci peut être utilisé
pour ajouter des commentaires dans le fichier.

### Date
La date est au format `YYYY-MM-DD`. Elle indique la date à laquelle le travail
a été effectué. C'est cette colonne qui est utilisée pour déterminer quelles
entrées doivent être utilisées pour déclarer les heures travaillées à Paul.
Notez que la date exacte n'a pas d'importance, seuls le mois et l'année sont
pris en compte.

### Heures
Le nombre d'heures travaillées ce jour là. Ce peut être un nombre à virgule. Il
est multiplié par le taux-horaire pour estimer le chiffre d'affaire lié à cette
entrée.

### Taux horaire
La rémunération horaire de cette entrée. Ce peut être un nombre à virgule. Elle
est multipliée par le nombre d'heures pour obtenir le chiffre d'affaire.

# Améliorations possibles

- Tester le support d'autres serveurs mail que GMail pour l'envoi.
- Support d'autres cas de remplissage du formulaire, notamment pour les
  auto-entepreneurs.

Contributions welcome.
