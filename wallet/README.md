# Wallet and tap card

The practical design has three independent pieces:

1. The existing HTTPS URL remains the source of truth.
2. Apple Wallet and Google Wallet cards render that URL as a QR code.
3. A passive NFC tag on the phone or case stores the same URL as an NDEF URI.

Passkeys are authentication credentials and are not part of this flow. Standard
Wallet passes cannot open a URL on another phone over NFC: Apple pass NFC is for
Apple Pay/VAS terminals and requires a special entitlement; Google Smart Tap is
for certified redemption terminals. A URL-programmed NFC tag is the simple,
cross-platform way for another iPhone or Android phone to tap and open the site.

## Configuration

Copy `.env.example` to `.env` and set `RESUME_URL` and `PASS_LABEL`. The URL is
public by design, while `.env`, credentials, and generated passes stay out of
Git.

## Apple Wallet

In the Apple Developer portal, register a Pass Type ID and create its Pass Type
ID certificate. Export/convert the certificate and private key to PEM, download
the current Apple WWDR intermediate certificate, configure their paths in
`.env`, then run:

```sh
python3 wallet/build.py apple
```

Open `wallet/out/resume.pkpass` on the iPhone to add it to Wallet. The pass is
fully static: no app, server-side pass service, database, or push updates.

## Google Wallet

Create a Google Wallet issuer account, enable the Wallet API, authorize a Google
Cloud service account in the Wallet console, and save its JSON key under
`credentials/`. Configure the issuer ID and key path in `.env`, then run:

```sh
python3 wallet/build.py google
```

Open the URL stored in `wallet/out/google-wallet.url` on the Android phone.
Google starts new issuers in demo mode; request publishing access before issuing
the pass outside configured test accounts.

## Phone-to-phone tap

Use an NTAG213/215/216 NFC sticker intended for mounting on a phone case. In any
NDEF writer app, write exactly one URI record containing `RESUME_URL`, lock the
tag only after testing, and place it away from the phone's own NFC antenna. The
receiver does not need an app; current iPhones and Android phones recognize URL
records directly. Keep the QR code as the universal fallback.
