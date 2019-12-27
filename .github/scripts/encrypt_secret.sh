#!/bin/sh

# Decrypt the file
# --batch to prevent interactive command --yes to assume "yes" for questions
rm ./translations.json.gpg
gpg --passphrase "$api" --batch --symmetric --cipher-algo AES256 ./translations.json
