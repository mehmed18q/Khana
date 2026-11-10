# Offline spelling dictionaries

- `fa-IR.{aff,dic}`: Lilak Persian dictionary from [LibreOffice/dictionaries](https://github.com/LibreOffice/dictionaries), commit `c0865a85eb67dc377f2cf8e8fe2c4fa9e53f0dcb`, directory `fa_IR`. Apache-2.0; see LICENSE-fa.txt and README-fa.txt.
- `en-US.{aff,dic}`: Ubuntu hunspell-en-us / SCOWL, copied from `/usr/share/hunspell/en_US.{aff,dic}`. See LICENSE-en.txt for notices.
- `ar.{aff,dic}`: Ayaspell Arabic dictionary from [LibreOffice/dictionaries](https://github.com/LibreOffice/dictionaries/tree/c0865a85eb67dc377f2cf8e8fe2c4fa9e53f0dcb/ar), commit `c0865a85eb67dc377f2cf8e8fe2c4fa9e53f0dcb`. Distributed under the LGPL-2.1-or-later option of its GPL/LGPL/MPL tri-license; see LICENSE-ar.txt, LGPL-2.1.txt, AUTHORS-ar.txt and README-ar.txt. The linked upstream files are the corresponding source.

The original, unmodified Hunspell files are loaded by Spylls in a background worker. No text is sent to a service. All three dictionaries and licenses are included by `packaging/khana.spec`. Persian and Arabic words using shared letters are accepted if either dictionary recognizes them. Arabic vocalization marks and tatweel stay in the editor and are handled by the dictionary's IGNORE rules.
