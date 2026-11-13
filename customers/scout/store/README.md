# Scout: Play Store listing

Upload these in Play Console → Grow → Store presence → Main store listing (or with fastlane `supply`,
which uses this folder layout).

| File | Play Console field | Limit |
|---|---|---|
| `en-US/title.txt` | App name | 30 characters |
| `en-US/short_description.txt` | Short description | 80 characters |
| `en-US/full_description.txt` | Full description | 4000 characters |
| `images/icon.png` | App icon (512 × 512 PNG) | |
| `images/featureGraphic.png` | Feature graphic (1024 × 500) | |

The app name must stay exactly `Scout: Field Data & Insights` (it matches `app.store_name` in
`customer.yml`; the build checks both). The name under the phone icon stays **Scout**.

Phone screenshots (at least 2) are still needed: take them from the installed app.
`source/` holds the files the images were made from.
