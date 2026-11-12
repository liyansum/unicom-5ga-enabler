# Third-party components and payloads

- `tools/airlift_engine.py` is adapted from [YiHoooong/AirliftSilence](https://github.com/YiHoooong/AirliftSilence), licensed under MIT. Its notice is retained in `third_party/AirliftSilence-LICENSE.txt`. This copy includes carrier-tool permission handling and privacy changes. The upstream credits Johnny Franks' airlift, Guy Dahan's Windows port, and Mak5er's AirCard-iOS work.
- The static Grappa client tokens in the Airlift engine are public protocol constants from [Mak5er/AirCard-iOS](https://github.com/Mak5er/AirCard-iOS), already included by the upstream project. They are not a user's device pairing record or account token.
- [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) is GPL-3.0-or-later. The source dependency is pinned in `requirements.txt`; the portable release retains installed package source, metadata and license notices.
- Python is distributed under its own license. The portable release retains `runtime/LICENSE.txt` and the included libraries' license notices.
- Apple Mobile Device Support, iTunes and Apple DLLs must be installed separately and are not bundled.
- Carrier/IPCC, PRI, carrier signature data and related payloads remain the property of Apple and the relevant carrier. The code license does not grant additional rights to these data files. Payload version and hashes are recorded in `original_ipcc.json` and `payloads.json`.

The repository's own Python scripts, batch launcher, tests and documentation are licensed under GPL-3.0-or-later unless an included file states otherwise. Third-party files retain their original licenses.
