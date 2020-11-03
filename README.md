# Bot d'actualisation de situation Pôle Emploi

Ce programme rempli automatiquement le formulaire d'actualisation sur le site
de Paul. Pour l'instant, il remplit le formulaire toujours de la même façon en
répondant "Oui" à "Etes-vous toujours à la recherche d'un emploi ?" et "Non" à
toutes les autres.

En cas de succès il envoie un mail à l'adresse indiquée avec un résumé de
l'actualisation. En cas d'échec, il envoie un rapport d'erreur au compte gmail
utilisé pour l'envoi des mails. Il utilise uniquement un compte gmail pour
l'envoie de mails.

# Utilisation

L'utilisation prévue est de lancer le bot tous les mois avec une entrée cron
telle que suit:

    0 8 1 * * dir/to/autovalidate.py youraccount@gmail.com GMa1lP4s5W0rD destionation@mail.com loginPE p4ssw0rdPE

- `youraccount@gmail.com` et `GMa1lP4s5W0rD` correspondent respectivement au
login et mot de passe du compte gmail d'envoi.
- `destination@mail.com` est l'adresse mail où sera envoyé le résumé de
l'actualisation si tout se passe comme prévu.
- `loginPE` et `p4ssw0rdPE` sont les login et mot de passe sur le site de Paul
Emploi tel que mis en place depuis l'été 2019.

# Améliorations possibles

- Fichier de configuration à la place des arguments de la ligne de commande.
- Support d'autres serveurs mail que GMail pour l'envoi.
- Support d'autres cas de remplissage du formulaire, notamment pour les
  auto-entepreneurs.

Contributions welcome.
