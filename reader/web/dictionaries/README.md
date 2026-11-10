# Offline spelling dictionaries

- `fa-IR.{aff,dic}`: Lilak Persian dictionary from [LibreOffice/dictionaries](https://github.com/LibreOffice/dictionaries), commit `c0865a85eb67dc377f2cf8e8fe2c4fa9e53f0dcb`, directory `fa_IR`. Apache-2.0; see LICENSE-fa.txt and README-fa.txt.
- `en-US.{aff,dic}`: Ubuntu hunspell-en-us / SCOWL, copied from `/usr/share/hunspell/en_US.{aff,dic}`. See LICENSE-en.txt for notices.

The original, unmodified Hunspell files are loaded by Spylls in a background worker. No text is sent to a service. Both dictionaries and licenses are included by `packaging/khana.spec`.
