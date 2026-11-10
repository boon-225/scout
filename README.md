# White-label field app pipeline

One config folder per client in, one signed Android app out.

This repository builds branded versions of [QField](https://github.com/opengisch/QField)
(GPL-2.0-or-later). QField's code is **never modified here**: every build checks out unmodified
QField at the version in `upstream.lock`, applies a client's branding from `customers/<client>/`,
then compiles and signs it.

| Client | App | App ID | Server |
|---|---|---|---|
| `scout` | Scout | `com.boonagric.scout` | https://cloud.boonagric.com |

## Layout

```
upstream.lock                 QField release every client is built from (e.g. v4.3.7)
customers/<client>/
  customer.yml                everything that differs between clients
  assets/logo.svg             square logo (About page, cloud sign-in, default avatar)
  assets/android/             launcher icon, splash and notification icon (vector drawables)
customers/_template/          copy this to start a new client
branding/apply.py             applies one client's branding to a clean QField checkout
branding/rebrand_ids.sh       app ID, name, default server
branding/rename_texts.py      on-screen wording (QField -> app name)
branding/overlays/            replacement screens (About page)
tools/make_wordmark_assets.py placeholder logo assets from the app name (until real logos arrive)
tools/dry_run.sh              apply + scan a client locally, without compiling
.github/workflows/build.yml   build one client (manual) or release (tag <client>-v1.2.3)
.github/workflows/check.yml   quick check of every client on each push (no compiling)
```

## Build a client

* **Test build:** Actions → **Build app** → Run workflow → client `scout`. The APK is attached
  to the run (unsigned debug APK if the client's signing secrets are not set).
* **Release:** push a tag `scout-v1.0.0`. The signed APK goes to a GitHub Release; the Play Store
  bundle (`.aab`) is attached to the run.

The first build compiles all dependencies (about 5 hours) and caches them for every client.
If it stops at the time limit, use **Re-run all jobs**; it continues from the cache.

### Signing secrets (per client)

Settings → Secrets and variables → Actions, with the client key in capitals:

| Secret | Value |
|---|---|
| `SCOUT_KEYSTORE_B64` | the client's `.p12` keystore, base64-encoded |
| `SCOUT_KEY_ALIAS` | key alias inside the keystore |
| `SCOUT_KEYSTORE_PASS` | keystore password |

**One key per client, kept forever.** Updates must be signed with the same key. Keep the keystore
and its password in a vault plus two offline backups. Never commit them; `.gitignore` blocks the
common file types.

## What branding changes (`branding/apply.py`)

1. App name, app ID and default server.
2. On-screen wording: "QField" → app name, "QFieldCloud" → cloud name (all languages).
3. QField documentation and product-site links → the client's help page; "Reach out" → support email.
4. About page → client logo, organisation, support, privacy link, open-source notice.
5. Disabled: QField documentation search, mascot easter egg, translator link, QField plugin catalogue.
6. Logos, launcher icon, splash, notification icon; colours (theme).
7. Sample projects off; Android notification titles renamed.
8. `NOTICE.md` (GPL notice and list of changed files).
9. **Scan:** the build stops if any user-visible QField name or link is left
   (when `upstream_name.visible: false`).

Every patch checks the code it changes still matches what it was written for; if a new QField
release changes it, the build stops with a message saying which patch to review.

## Add a client

1. `cp -r customers/_template customers/<client>` and fill in `customer.yml`.
2. Add logo assets (or run `python3 tools/make_wordmark_assets.py customers/<client>/customer.yml`
   for placeholders).
3. `tools/dry_run.sh <client>` (or push and let **Check branding** run).
4. Create the client's signing key and add its three secrets.
5. Run **Build app** for the client and test on a phone.

## Update QField

Change `upstream.lock` (e.g. to the next release), push, and let **Check branding** run. If a
patch reports that QField changed, update it, then build every client.

## Licence

QField is © OPENGIS.ch and contributors, GPL-2.0-or-later. Built apps are distributed under the
same licence (see `LICENSE` and each build's `NOTICE.md`). The scripts in this repository are
GPL-2.0-or-later. Client names and logos belong to their owners.
