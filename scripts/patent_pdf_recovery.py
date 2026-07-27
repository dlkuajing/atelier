"""Fail-closed recovery of patent drawing tables from public PDF images.

USPTO Patent Public Search serves some drawing tables only as page images.  A
Google Patents PDF may add an OCR text layer to the same page image.  This
module accepts that text layer only when every decoded page raster is pixel-
identical to the official USPTO PDF, then retains a second deterministic OCR
view of the key pages for missing-cell detection and parser provenance.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import io
import json
import re
from dataclasses import dataclass
from typing import Any

import cv2
import httpx
import numpy as np
import pypdf
from rapidocr_onnxruntime import RapidOCR

USPTO_IMAGE_PDF_URL = (
    "https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/{patent_number}"
)
GOOGLE_PATENT_URL = "https://patents.google.com/patent/{compact_publication_id}/en"
GOOGLE_PDF_HOST = "patentimages.storage.googleapis.com"
_GOOGLE_PDF_META_RE = re.compile(
    r'<meta\s+name="citation_pdf_url"\s+content="(?P<url>[^"]+)"',
    flags=re.IGNORECASE,
)
_ABILITY_REQUIRED_FIGURE_TEXT = (
    "FIG. 2A lists one embodiment",
    "FIG. 2B lists another embodiment",
    "FIG. 5 lists one embodiment",
    "FIG. 7 lists information",
)
_ABILITY_EIGHT_LENS_REQUIRED_FIGURE_TEXT = (
    "FIG. 2 shows each lens parameter of the optical lens",
    "FIG. 3 lists aspheric coefficients of the mathematic equation "
    "of the aspheric lenses of the optical lens",
    "FNO is F-number of the stop STO",
    "FOV is a field of view of the optical lens",
)
_ABILITY_EIGHT_LENS_PROFILE = "ability_eight_lens_metadata_unpublished_v1"
_ABILITY_THREE_LENS_REQUIRED_FIGURE_TEXT = (
    "FIG. 4A lists parameters of each lens of the optical lens shown in FIG. 1",
    "FIG. 4B lists aspherical coefficients of the aspherical surface formula "
    "of the lenses in optical lens shown in FIG. 1",
    "FIG. 5A lists parameters of each lens of the optical lens shown in FIG. 2",
    "FIG. 5B lists aspherical coefficients of the aspherical surface formula "
    "of the lenses in optical lens shown in FIG. 2",
    "FIG. 6A lists parameters of each lens of the optical lens shown in FIG. 3",
    "FIG. 6B lists aspherical coefficients of the aspherical surface formula",
    "FIG. 7 lists optical data of the optical lenses OL 1 , OL 2 , OL 3",
)
_ABILITY_THREE_LENS_PROFILE = "ability_three_lens_prescriptions_v1"
_ABILITY_THREE_FIVE_LENS_PROFILE = (
    "ability_three_five_lens_angular_field_unpublished_v1"
)
_ABILITY_THREE_FIVE_LENS_BINDING_PATTERNS = {
    "surface_ol1": r"FIG\s*\.\s*4\s*A\s+lists\s+each\s+lens\s+parameter",
    "asphere_ol1": r"FIG\s*\.\s*4\s*B\s+lists\s+aspheric\s+coefficients",
    "surface_ol2": r"FIG\s*\.\s*5\s*A\s+lists\s+each\s+lens\s+parameter",
    "asphere_ol2": r"FIG\s*\.\s*5\s*B\s+lists\s+aspheric\s+coefficients",
    "surface_ol3": r"FIG\s*\.\s*6\s*A\s+lists\s+each\s+lens\s+parameter",
    "asphere_ol3": r"FIG\s*\.\s*6\s*B\s+lists\s+aspheric\s+coefficients",
    "system_meta": r"FIG\s*\.\s*7\s+lists\s+optical\s+information",
}
_ABILITY_THREE_FIVE_LENS_ROLE_PAGES = {
    "ability_three_five_prescription_ol1": 4,
    "ability_three_five_prescription_ol2": 5,
    "ability_three_five_prescription_ol3": 6,
    "ability_three_five_system_meta": 7,
}
_ABILITY_THREE_FIVE_LENS_SOURCE_LAYOUTS: dict[str, dict[str, Any]] = {
    "f43a4a419a082df67f60af279a3053069903b81eac017ba14d55359904840987": {
        "application_number": "16/883126",
        "normalized_text_sha256": (
            "9a41a01aeb9a626685aa3a7939d2c34c3dd442573accf78a2de062fb73b72910"
        ),
        "page_count": 13,
        "blank_mirror_pages": frozenset(range(1, 14)),
        "page_image_sha256": (
            "6ce17af05bcb10833f82327e7fcc15993652daad569928ea65a7a5fb43ec7d40",
            "68719a082f41eb68aaaef42690f7b931ad73cc25845c247e8e66f1665d23287b",
            "42710a6e86ccd32178768109e1122284481136c588df4bf1a1cdc9bac7eb28e1",
            "055d03af44b5645747398e2a8909828d0d8daa9eb5ad450435c005ddfaafd318",
            "d228c17cc75a9ee07221c983939fe84a2c52227b946d4973a8b4b9a76c7f1fbc",
            "07969a02deff4c2b837b465d7218e1ef992b4f0e4b34578efbb1a90b0070ea28",
            "71d564b5a924d610faf1434749a7798fb097923815b32960fb94cf5f6874354d",
            "f9d78791e50b3bb8f6aeb5b913f8e7727f6c58d566d3b334fe8dcf33fc4f7206",
            "8f4495e97a5fefd284b21f2d42852f2be99f5455aa01aa103bfea012398828fb",
            "58b3d6cac78c6ec13eb3f2901749a8ca0a066f161703a4c53d5adc7640b1aa19",
            "c556278d8db31888f2c024eaed389cb3a7b00b35bde1568b038f5195878e140d",
            "149e068f56da88775fa69646af80ee8b2a510f9380fbdd804aa96022a48549c5",
            "352d79924a39529657d9af653e0875c8330ff05adf369f7d89a512f648f1a8cb",
        ),
    },
    "a94cba4e581ebdb5b65798212ca6211170174ac43d60e539cce2152cf9d6c8de": {
        "application_number": "16/883126",
        "normalized_text_sha256": (
            "49c30c4ae4049648ef33fd99bc6a5eb0f00c4da7f6e9c97949f5f1dc041e68d1"
        ),
        "page_count": 13,
        "blank_mirror_pages": frozenset(),
        "page_image_sha256": (
            "667562164dc4ad02135f661fc336d574ffd2b8e2362465ecaa06acd72b7bd968",
            "085e01c20df7f66bdc7f90b1d7935c2c4505511787cc83385d2d300b267260a3",
            "02f2c8c7e283316db6f2324345fadf4440f824ded7815e867fbea280b2e5c390",
            "d20d9ff892f922c5ad176338e64c05d02a966b30f0bf6e359b9db89c4e4c1add",
            "95742709b43e371b5f6c8bae4765cf46bea3609c5046d15de40742113c189c9b",
            "d4e2eb07042851f8025ea6037d2b654a1f2941c248ad64dfba28683b4448abda",
            "bd904a31f239fb583b2183d901dbeb37a9a30769938a548b728a4f11d9da51d9",
            "c2cf657990d7773f275578e988a59797a43803bcb086ac335eb0ee1fc805b23c",
            "71cfb7959d7a019816dc2b363a8cfcaf681895eaaa6fc7316fc1d20cbe9745ca",
            "19fee2dd2903b2b4cc1c5a5bee9ea801846dd46fcea34a82578dbc86b42a674d",
            "f8dac69f7cfa9c1bce6931d56739b4757ed3ea81e72572e86636973453536766",
            "ee681be1a5f9c92b5728bff9dececa0eecf9fd5c9050a8ea3bd452006409b4b7",
            "c2acca3b6f1d89bf8f79a8f7925d6ce5c65473351b7ca8f000ee8c627b10c19c",
        ),
    },
}
_ABILITY_FOUR_WIDE_ANGLE_PROFILE = "ability_four_wide_angle_prescriptions_v1"
_ABILITY_FOUR_WIDE_ANGLE_BINDING_PATTERNS = {
    "surface_ol1": r"FIG\s*\.\s*3\s*A\s+lists\s+each\s+lens\s+parameter",
    "asphere_ol1": r"FIG\s*\.\s*3\s*B\s+lists\s+aspheric\s+coefficients",
    "surface_ol2": r"FIG\s*\.\s*4\s*A\s+lists\s+each\s+lens\s+parameter",
    "asphere_ol2": r"FIG\s*\.\s*4\s*B\s+lists\s+aspheric\s+coefficients",
    "surface_ol3": r"FIG\s*\.\s*7\s+lists\s+each\s+lens\s+parameter",
    "surface_ol4": r"FIG\s*\.\s*8\s+lists\s+each\s+lens\s+parameter",
    "system_meta": r"FIG\s*\.\s*9\s+lists\s+the\s+specific\s+parameters",
}
_ABILITY_FOUR_WIDE_ANGLE_ROLE_PAGES = {
    "ability_four_wide_prescription_ol1": 2,
    "ability_four_wide_prescription_ol2": 3,
    "ability_four_wide_prescription_ol3": 5,
    "ability_four_wide_prescription_ol4": 6,
    "ability_four_wide_system_meta": 7,
}
_ABILITY_FOUR_WIDE_ANGLE_SOURCE_LAYOUTS: dict[str, dict[str, Any]] = {
    "d3357394ccefdb4090c9d5b607403cd512476db65630c5c51e812b7dd8ba8962": {
        "application_number": "17/364492",
        "family_id": "81258214",
        "normalized_text_sha256": (
            "aa900faf648f952352ff44833795275d2bacb74631279f798fbe7d478846a33c"
        ),
        "page_count": 15,
        "blank_mirror_pages": frozenset(),
        "page_image_sha256": (
            "4ef52ae5d6852de547aa472d6f1b06e0371cb0d2183427c60a968194db717f75",
            "3c637fadb8e75f8c26345d5e23646df6d41f8b24ec306fdf5088d97e3b4156d0",
            "09f6afdc224b74d847887a94b99981ff8b38910e25723b1211f602753bbc1cde",
            "cb4a63306832a0b5cf2aecd01a1da9e2e271301d6f7d8153a727fd2267070585",
            "9371c416e210e0a261f18ab18829f25f209f08e61cf0142303f9b2e9e5f5091b",
            "a2606c3749d2ce4a9daa7675e5fb3d92c28ffc07a653c624b60ce51110605059",
            "43b1fea857b9f02b1548828ba6957770702c70196c74bb377bac72b667c3703b",
            "ffc7ba9d6ecb54ab4b61e698848c3f40f40a41703da0058d46307269e1eb96e6",
            "ec52a3f6cf8c9220f70befbc7e664c9cb9b2c3d3ade4998ddb5490266f708e1f",
            "129f5497ef90829b1a7193108528fe53c85a0703373bb8da814759d66be41b8f",
            "69a797c0f10cf6fa32ddf9a1aeb74c5e101a0fe5930a8ee911f830c37fab621d",
            "dcb63d8b3b00281b56e4c964f65ef5f5b454b2464318bb16dd21fb5403609e3b",
            "b47421f3d07ef9914d0bde508bc84eeec633a1e338f1c7ad8a96fd8fad11d8db",
            "ee7f34aa4ee49e3e2c5a9cfe279c577f5ead8bcc7773ba5b838dd37e81404e79",
            "880f8774647ac0eb1e1925c45458d62fd3a7dda32116e53e609cdae39327e231",
        ),
    },
}
_ABILITY_TWO_FIVE_LENS_REQUIRED_FIGURE_TEXT = (
    "FIG. 3A shows each lens parameter of the optical lens of FIG. 1",
    "FIG. 3B shows each coefficient of a mathematical formula of aspheric surface "
    "for the aspheric lens of the optical lens of FIG. 1",
    "FIG. 4A shows each lens parameter of the optical lens of FIG. 2",
    "FIG. 4B shows each coefficient of a mathematical formula of aspheric surface "
    "for the aspheric lens of the optical lens of FIG. 2",
    "FIG. 5 shows parameter performance of the optical lens",
)
_ABILITY_TWO_FIVE_LENS_PROFILE = "ability_two_five_lens_prescriptions_v1"
_ABILITY_TWO_NINE_LENS_REQUIRED_FIGURE_TEXT = (
    "FIG. 4A lists each lens parameter of the optical lens of FIG. 1",
    "FIG. 4B lists coefficients of the mathematic equation of the aspheric surfaces "
    "of the optical lens of FIG. 1",
    "FIG. 5A lists each lens parameter of the optical lens of FIG. 2",
    "FIG. 5B lists coefficients of the mathematic equation of the aspheric surfaces "
    "of the optical lens of FIG. 2",
    "FIG. 6 lists optical information of the optical lenses OL 1 and OL 2",
)
_ABILITY_TWO_NINE_LENS_PROFILE = "ability_two_nine_lens_f_number_unpublished_v1"
_ABILITY_FOUR_EIGHT_LENS_REQUIRED_FIGURE_TEXT = (
    "FIG. 2A lists parameters of each lens of the optical lens in FIG. 1",
    "FIG. 2B lists aspherical coefficients of the aspherical surface formula "
    "of the lenses in optical lens shown in FIG. 1 and FIG. 2A",
    "FIG. 4A lists parameters of each lens of the optical lens in FIG. 3",
    "FIG. 4B lists aspherical coefficients of the aspherical surface formula "
    "of the lenses in optical lens shown in FIG. 3 and FIG. 4A",
    "FIG. 6A lists parameters of each lens of the optical lens in FIG. 5",
    "FIG. 6B lists aspherical coefficients of the aspherical surface formula "
    "of the lenses in optical lens shown in FIG. 5 and FIG. 6A",
    "FIG. 8 lists parameters of each lens of the optical lens in FIG. 7",
    "FIG. 9 lists optical properties of the optical lenses",
)
_ABILITY_FOUR_EIGHT_LENS_PROFILE = "ability_four_eight_lens_f_number_unpublished_v1"
_ABILITY_FIVE_THREE_LENS_ORDINALS = (
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
)
_ABILITY_FIVE_THREE_LENS_SURFACE_FIGURES = (3, 7, 11, 15, 19)
_ABILITY_FIVE_THREE_LENS_ASPHERE_FIGURES = (4, 8, 12, 16, 20)
_ABILITY_FIVE_THREE_LENS_REQUIRED_FIGURE_TEXT = tuple(
    marker
    for ordinal, surface_figure, asphere_figure in zip(
        _ABILITY_FIVE_THREE_LENS_ORDINALS,
        _ABILITY_FIVE_THREE_LENS_SURFACE_FIGURES,
        _ABILITY_FIVE_THREE_LENS_ASPHERE_FIGURES,
        strict=True,
    )
    for marker in (
        f"FIG. {surface_figure} shows a table of optical parameters for optical lens "
        f"elements and a filter of the {ordinal} embodiment",
        f"FIG. {asphere_figure} shows a table of parameters for aspheric surfaces "
        f"of the {ordinal} embodiment",
    )
) + (
    "FIG. 21 shows a table of optical parameters for the first, second, third, "
    "fourth and fifth embodiments of the optical lens assembly according to the "
    "disclosure",
)
_ABILITY_FIVE_THREE_LENS_PROFILE = (
    "ability_five_three_lens_f_number_unpublished_v1"
)
_AAC_TWO_THREE_LENS_PROFILE = "aac_two_three_lens_field_unpublished_v1"
_AAC_TWO_THREE_LENS_REQUIRED_FIGURE_TEXT = (
    "FIG. 1 is an illustrative structure of an imaging lens assembly related to a "
    "first embodiment of the present disclosure.",
    "FIG. 2 is an illustrative structure of an imaging lens assembly related to a "
    "second embodiment of the present disclosure.",
    "FIG. 3 shows a longitudinal spherical aberration curve, an astigmatic field "
    "curve and a distortion curve of the imaging lens assembly shown in FIG. 1",
    "FIG. 4 shows a longitudinal spherical aberration curve, an astigmatic field "
    "curve and a distortion curve of the imaging lens assembly shown in FIG. 2",
)
_AAC_TWO_THREE_LENS_ROLE_PAGES = {
    "aac_two_three_drawing_sheet_1": 1,
    "aac_two_three_drawing_sheet_2": 2,
}
_AAC_TWO_THREE_LENS_SOURCE_LAYOUTS: dict[str, dict[str, Any]] = {
    "d442fce31a21057546974505b5aa3e5361304ad8525afe7455a4cb438bfb5600": {
        "application_number": "14/832442",
        "normalized_text_sha256": (
            "99c5ebf699ef689f6769d12e6a755c33eda8e3fac4021eccdf3f36abf693213d"
        ),
        "page_count": 7,
        "blank_mirror_pages": frozenset(),
        "table_block_sha256": (
            "e2ec3a72c80cf18601e0ee782c9550d9feffd600aea8d06081b122c0955586f5",
            "5c1f1c74edb0ba1ffd97f8b5d86808d4cae516047cf9059cd533d1d3facdb386",
            "efb81b625b9f8f04857d955c7beee11576014688f8103baf4b312950bcc836e5",
            "01ff5df296ef054c678b06fa3a1db72a3c96446e724e0fc6a60a8fec22afe39a",
            "c006d1ce1ef4a7827d844fa46e812622007675de3b8473228d817430dc0812c5",
        ),
    },
    "cd5bc9f6cab04ac685e4dca612a9b974767d03f6021fd7527230bdbafc7d3047": {
        "application_number": "14/832442",
        "normalized_text_sha256": (
            "f4b1e6f46bcf5d0bb7ab11e94de42ab706d8a488f58df6cd6a572e54e0bf086f"
        ),
        "page_count": 7,
        "blank_mirror_pages": frozenset(),
        "table_block_sha256": (
            "d69322ee49d979453728e3c539d7d3183aa3e2194696493b2e067d64bdad983f",
            "7284512e5e41cef0396f8ed743fdad0db2f51b61ecc1d4c2ca50430c7686d49a",
            "fe5eac295bf9b7dc5a45ad7cc26919d80f1e1ce507053800862a2009e0e0dfc0",
            "c76b393f657e9556021def9b4de7cb2df010736be818ecb60797f490748e9700",
            "a1263ba358ad89aec023c81b6cee8073f8fdf2968987eb7f3f5af4b99a2ce94b",
        ),
    },
}
_ABILITY_FIVE_THREE_LENS_SOURCE_LAYOUTS: dict[str, dict[str, Any]] = {
    "a389c98016a9f5af18165a30a2041fe29a761d3d37958ffce100e8bfb81ea50d": {
        "application_number": "14/858521",
        "normalized_text_sha256": (
            "a7a4d8d7489ef8db8b76b64868fdcf31cfc32b37934a5c17f39484893f212b1f"
        ),
        "page_count": 27,
        "blank_mirror_pages": frozenset(),
    },
    "e9fee581375c0ca2c0946fe8b27032c078f14aa82e90aa6365889cd4667319f0": {
        "application_number": "14/858521",
        "normalized_text_sha256": (
            "5089537a9bb04df736b4cef2a4146e377b92aced134d7432870fddde145b205c"
        ),
        "page_count": 26,
        "blank_mirror_pages": frozenset({3, 4, 12, 17, 21}),
    },
}
_ABILITY_FIVE_THREE_LENS_ROLE_PAGES = {
    **{
        f"ability_five_three_surface_{embodiment}": page_number - 1
        for embodiment, page_number in enumerate((4, 8, 12, 16, 20), start=1)
    },
    **{
        f"ability_five_three_asphere_{embodiment}": page_number - 1
        for embodiment, page_number in enumerate((5, 9, 13, 17, 21), start=1)
    },
    "ability_five_three_meta": 21,
}
_LARGAN_THREE_FIVE_LENS_REQUIRED_FIGURE_TEXT = (
    "FIG. 7 is TABLE 1 which lists the optical data of the first embodiment",
    "FIG. 8 is TABLE 2 which lists the aspheric surface data of the first embodiment",
    "FIG. 9 is TABLE 3 which lists the optical data of the second embodiment",
    "FIG. 10 is TABLE 4 which lists the aspheric surface data of the second embodiment",
    "FIG. 11 is TABLE 5 which lists the optical data of the third embodiment",
    "FIG. 12 is TABLE 6 which lists the aspheric surface data of the third embodiment",
    "FIG. 13 is TABLE 7 which lists the data of the respective embodiments",
)
_LARGAN_THREE_FIVE_LENS_PROFILE = "largan_three_five_lens_prescriptions_v1"
_ABILITY_ZOOM_TWO_STATE_REQUIRED_FIGURE_TEXT = (
    "FIG. 3 lists each lens parameter of the optical lens at the telescopic end "
    "shown in FIG. 1",
    "FIG. 4 lists each lens parameter of the optical lens at the wide-angle end "
    "shown in FIG. 2",
    "FIG. 5 lists aspheric coefficients of the mathematic equation of the aspheric "
    "lenses of the optical lens of FIG. 1",
    "FIG. 6 lists the specific parameters of the optical lens of FIG. 1",
)
_ABILITY_ZOOM_TWO_STATE_PROFILE = "ability_zoom_two_state_census_v1"
_SNAP_SIX_LENS_TWO_DESIGN_PROFILE = "snap_six_lens_two_design_ocr_review_v1"
_SNAP_SIX_LENS_TWO_DESIGN_REQUIRED_TEXT = (
    "FIGS. 4 and 5 include tables showing a prescription of a first sample "
    "imaging lens assembly design",
    "FIGS. 6 and 7 include tables showing a prescription of a second sample "
    "imaging lens assembly design",
    "Design 1 omits the optional second element.",
    "Design 2 includes the optional second element.",
    "effective focal length of 1.57 mm",
    "field of view is set to 115 degrees at a diagonal, with 120 degrees to an "
    "image circle",
    "f-number of the imaging lens assembly 10 is 2.4",
    "At an image height of 1.98 mm",
)
_SNAP_SIX_LENS_TWO_DESIGN_SOURCE_LAYOUTS: dict[str, dict[str, Any]] = {
    "7910d5bca19dc438a5ca8b159eb45327adc1e3aff91670babfde68745c4e8fd3": {
        "application_number": "16/483973",
        "normalized_text_sha256": (
            "d675c20e5301723fb831bf0f842f66eabf5d210da4d28336e1a7413a5f1e1e63"
        ),
        "page_count": 19,
        "blank_mirror_pages": frozenset(),
        "role_pages": {
            "snap_power_ranges": 4,
            "snap_surface_design_1": 5,
            "snap_asphere_design_1": 6,
            "snap_surface_design_2": 7,
            "snap_asphere_design_2": 8,
        },
        "page_image_sha256": (
            "486d2f2040192bb53af69337d8d374b928fc365f4378ea6e5d335667ba5271d9",
            "909ddfec82ad0b5246a7e4f0d25b52bee7e532c6ba38f1b3440b9d1c4d9596db",
            "eaca5b50fea4b279c35d8a317094e21ca0cf6e1b3adcb38f858602b4dc232715",
            "544d4c74c7ab8cfabb9aeb809e7a876cc3b9d0cf69a2e16f1633711b17a9af9f",
            "8824110fa208d5c9925895403da341ddf6ac5a38158d652b60ee432f0a83c08f",
            "49745b8de3d0aa105b624f2926d353a7b49083fb24ad6b0114fcf6ec8cebac45",
            "b4bf0c8478b2362eba3cb3c9a70554b73812525f0d04beb621536e00552e8de1",
            "bfd126b5b583905013d02a12dc2f860a0e5ccea165073a4e37e366e30cc0f58c",
            "e8063fe29aa0fd8630b95ec33046a34c1c0c1e3d6b38b84b8d0f4adca1aa2c9f",
            "a146bbd217172444573359ee5c0f791c15daed459aeab45bb80b9ae7d8a23e6b",
            "d93261af1f9db18fc7e151705f40d179d26863a32c9afec9005687f9efb223cb",
            "4811237defcdde958ca706cc415370889afcf6da32966f87be12a7881414b18c",
            "970beb6790a24c964031488f1283fd92441482c50c8047346b6934cb3ae0a720",
            "21f1c25557131ba545e295b282dc1a520a22d32e2dca5961483d711476b5183f",
            "581719c17f076c09b6cc8daec52f112ef02b4a7fb9dcb1dbe0ed57e020278e24",
            "0991732fc27a1dcc0c5e2a5e957272429aa8e39b2283104ddc34a23fe49f0b51",
            "83b634ced52d066a4b1f79e32552cf476a224eb743845c49340bec8e490cf81d",
            "748df2a637820c92832d3d932a790a631aa62363654b4d72e7c1c35b4a02632e",
            "388519915fcad6bb07ff1a995fa0823a7c2d0f7a41b710157d0d38235f4147f6",
        ),
    }
}
_CIRCLE_OPTICS_SEVEN_LENS_REQUIRED_TEXT = (
    "provide lens prescription data for the lens",
    "A prescription for this camera lens is given",
    "with glass or material types, axial thicknesses, and surface radii identified",
    "The lens has 7 lens elements",
    "Aspherical surface coefficients are also provided",
    "focused image at F/2.0",
    "nominal focal length of 2.57 mm",
    "aperture stop diameter of 1.42 mm",
)
_CIRCLE_OPTICS_SEVEN_LENS_PROFILE = "circle_optics_seven_lens_ocr_review_v1"
_CIRCLE_OPTICS_SEVEN_LENS_SOURCE_LAYOUTS: dict[str, dict[str, Any]] = {
    "f39a32f7a1eb5004447f43fc12e3bd60c06a55f4f4c50d26e4375e61b17bd154": {
        "application_number": "17/622463",
        "page_count": 66,
        "role_pages": {
            "circle_optics_surface_table": 16,
            "circle_optics_asphere_table": 17,
        },
    },
    "449f9a8e066cb4625dd38d76d737a711f216fb45195668f98c25f9c32cebabf4": {
        "application_number": "19/217645",
        "page_count": 66,
        "role_pages": {
            "circle_optics_surface_table": 15,
            "circle_optics_asphere_table": 16,
        },
    },
}
_KODAK_LOW_STRESS_REQUIRED_TEXT = (
    "FIG. 14A is a table specifying the lens design parameters for the third "
    "exemplary projection lens of FIG. 12A",
    "FIG. 14B is a table specifying the lens design parameters for the third "
    "exemplary relay lens of FIG. 12C",
    "The prescription for the third exemplary projection lens 270, shown in FIG. "
    "12A, is provided in the table of FIG. 14A, with the data for radii (lens shape "
    "or curvature), thicknesses, and materials included.",
    "All the lens surfaces have spherical, rather than aspheric, toric, or "
    "cylindrical profiles.",
    "The prescription for the third exemplary relay lens 250, shown in FIG. 12C, "
    "is provided in the table of FIG. 14B, with the data for radii, thicknesses, "
    "and materials included.",
    "The lens designs prescribed in FIGS. 14A and 14B, and shown in FIGS. 12A and "
    "12C, were fabricated, assembled, and tested",
)
_KODAK_LOW_STRESS_F_NUMBER_CONTEXTS = (
    "relay lens 250 is designed to collect and image F/6 light",
    "projection lens 270 is preferably a faster lens (.about.F/3) than the relay "
    "lens 250",
    "projection lens 270 operates at F/2.5 or faster",
)
_KODAK_LOW_STRESS_TWO_LENS_PROFILE = (
    "kodak_low_stress_two_lens_metadata_unpublished_v1"
)
_KODAK_LOW_STRESS_SOURCE_LAYOUTS: dict[str, dict[str, Any]] = {
    "2efe34e5641c40bcb2c93d330d9288271b19f2d851f1bba26e03aef85d269819": {
        "application_number": "14/042755",
        "normalized_text_sha256": (
            "8affd3aaf0079a69bd7d4a8e68fb31a653b857f6bcbd352b9666d696cd2be572"
        ),
        "page_count": 61,
        "blank_mirror_pages": frozenset({7, 23, 30, 34, 37, 39}),
        "role_pages": {
            "kodak_projection_prescription": 35,
            "kodak_relay_prescription": 36,
        },
    },
    "ddb70ad8434854ab534ae7fb26e1c015147b0ea1518c9ef792f5d112ede1c3e5": {
        "application_number": "12/784520",
        "normalized_text_sha256": (
            "1c2a2c4c9be26ae4aa04bcbb80595ea827d5252f89a37c7210e2dc68595c0c98"
        ),
        "page_count": 60,
        "blank_mirror_pages": frozenset({12, 14, 19, 21, 22, 26, 30, 39}),
        "role_pages": {
            "kodak_projection_prescription": 36,
            "kodak_relay_prescription": 37,
        },
    },
    "2e5c75ff60cb61628fb6c256aa18b23a43adbfc04a60fac0974f8a60027173e8": {
        "application_number": "14/042755",
        "normalized_text_sha256": (
            "e0196b6186bec0b637bfee3cfc5bdcad39fb273a9275e7894199cb5eff9f857e"
        ),
        "page_count": 61,
        "blank_mirror_pages": frozenset(
            {12, 14, 19, 22, 23, 24, 28, 29, 30, 31, 34, 35, 38, 39}
        ),
        "role_pages": {
            "kodak_projection_prescription": 36,
            "kodak_relay_prescription": 37,
        },
    },
}
_GENIUS_FOUR_LENS_SIX_ORDINALS = (
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
)
_GENIUS_FOUR_LENS_SIX_OPTICAL_FIGURES = (4, 8, 12, 16, 20, 24)
_GENIUS_FOUR_LENS_SIX_ASPHERE_FIGURES = (5, 9, 13, 17, 21, 25)
_GENIUS_FOUR_LENS_SIX_REQUIRED_FIGURE_TEXT = tuple(
    marker
    for ordinal, optical_figure, asphere_figure in zip(
        _GENIUS_FOUR_LENS_SIX_ORDINALS,
        _GENIUS_FOUR_LENS_SIX_OPTICAL_FIGURES,
        _GENIUS_FOUR_LENS_SIX_ASPHERE_FIGURES,
        strict=True,
    )
    for marker in (
        f"FIG. {optical_figure} is a table of optical data for each lens element of "
        + (
            "a first embodiment of an optical imaging lens according to the present disclosure"
            if ordinal == "first"
            else f"the optical imaging lens of a {ordinal} embodiment of the present disclosure"
        ),
        f"FIG. {asphere_figure} is a table of aspherical data of a {ordinal} embodiment "
        "of the optical imaging lens according to the present disclosure",
    )
)
_GENIUS_FOUR_LENS_SIX_COMPARISON_MARKER = (
    "FIG. 26 is a table for the values of (T3/G.sub.34), (T4/T2), (G.sub.23/T4), "
    "(G.sub.aa/ALT), [(T1+T3)/T4] and (EFL/ALT) of all six example embodiments"
)
_GENIUS_FOUR_LENS_SIX_DEVICE_MARKERS = (
    "FIG. 27 is a structure of an example embodiment of a mobile device",
    "FIG. 28 is a partially enlarged view of the structure of another example embodiment "
    "of a mobile device",
)
_GENIUS_FOUR_LENS_SIX_PROFILE = "genius_four_lens_six_embodiment_census_v1"
_GENIUS_FOUR_LENS_SIX_SOURCE_LAYOUTS: dict[str, dict[str, Any]] = {
    "cc17913116d0dc5ee3b49fcaf720e69824f8fd1cf2ea4c79aa94e8ae1c1da145": {
        "application_number": "14/608769",
        "family_id": "48495278",
        "normalized_text_sha256": (
            "62d6440ae13e941f8dff3394a3b998eefb8f42f9815352a9bf509809f4fdd0b2"
        ),
        "page_count": 36,
        "sheet_count": 27,
        "blank_mirror_pages": frozenset(),
        "owner_count": 1,
        "relationship_binding_counts": {
            "continuation_parent_application": 1,
            "related_parent_application": 1,
            "parent_grant": 1,
            "prior_publication": 0,
        },
        "role_pages": {
            **{f"genius_four_six_optical_{index}": page - 1 for index, page in enumerate((5, 9, 13, 17, 21, 25), 1)},
            **{f"genius_four_six_asphere_{index}": page - 1 for index, page in enumerate((6, 10, 14, 18, 22, 26), 1)},
            "genius_four_six_comparison": 26,
        },
        "role_sheets": {
            **{f"genius_four_six_optical_{index}": sheet for index, sheet in enumerate((4, 8, 12, 16, 20, 24), 1)},
            **{f"genius_four_six_asphere_{index}": sheet for index, sheet in enumerate((5, 9, 13, 17, 21, 25), 1)},
            "genius_four_six_comparison": 26,
        },
        "page_image_sha256": (
            "eba3e69c6a857c71a6abd8601b5cf2cd412584d4c105f6a89aa1a836008e5a03",
            "377a9a6ad8c2bc24662734a8dc8ac12ac659e3f2bbe1a199fa8571bdb8e43c76",
            "d438318e0ac8c13b03e26df1bc5862ecfab9bec904af4b62f019fa31aa988f66",
            "d43ac07c9c7008afb14e2e60f69bdf48b79a3540387da9881d0a38d6ac318883",
            "9d249fe0189a177db9ac81ffb6e2ad8ff575302b5ee8c7eaeec6c2ca0ee34f50",
            "ad8ac6f5d64829490ead75ea1dd1ba0b02d127279845fee91a477911412828d4",
            "6a5faeb25fc92bf0ea9d211cd6db72444ffdc9216727d5777f9f77884a8e27c4",
            "56251d7c302a49edcc79e9cfd53cb497e0cdad400f03380d81dafcc77ad13248",
            "5c6fbd73b319d021a462dc5bd855ce35fd6601f520953a344a65c52e9c255b3f",
            "404a0fbf51e1feaf5910f0d6d816bd9fe5d0a7fb638d016a6f87df1dee00b5d6",
            "6354d6d4007e06b136a1d54ff7a99e7185378f27e81875323efcc0c36e0825ea",
            "de551b289eb5f0fe73d7022aad15d2d89ce9313f957cd6f671e7a3b7da14c7d2",
            "9d676e82e1955a4242fa17ad035b6ef968cb2bf84cc677dff36d655d494312ce",
            "8edf03f46622f8434ab588966841f6064f079ec1bd4275eeba7d40070cc32c46",
            "2c7d797186fb8389b1b9d282d3865e5651fef49ccbb3b0f9397c05c768e5d58e",
            "de6e1e03958c3959840c89c2c10b94c0e3449ba74fb46b9b0998ddca8618b7cc",
            "138c6bd87a107fd0afa16051794b4e91b60afdfd0465a9e0b7d36d5a2af71c3e",
            "a65cd61e092da236863bb9fdcc25035bee601a7ce409871f940d701f40ef0c3f",
            "f7997f52517c35180fed021a7e233affb268df12fe7b57aeaae63a0e188e9d2a",
            "6ae1491a6ad9bb9aff40e62a29c6f9c80faf185f464ec6cc4caa048975f046f1",
            "843ddbd5225ac02a4d244b2af6413828e717131c1272f1b3fdcbd73f4aab36e1",
            "c02043c31390e270af7749ee4b755c8d8938d8928750f24ea5c1b44aac8bc42c",
            "b26c76db808d812b30b369d669d79f9a7668169bd46fb68df3359c2bb63c0f3c",
            "d167d5d291a6287883c242c8877be85601fa2b1ddd75efb600205d1a87dc744e",
            "393d0d646152ec61a109c6a91e0a031f7a3660964fb1eb79253d26e90f1c4f3e",
            "98f942afded933a52aa9e9f401860ccd99ef4edb3e870e8b1294b1892b6a53f6",
            "458b57fb31a6470ae9a0b6c64276d658775d0897d8cdc025207b1815939c8841",
            "643a3bb060d7e6228893e0308582bc24d6fe64ad3a6c5f503fc67da768cca043",
            "0aa5c7cb0b5032dd596fc622b51cedaf04bbd90ae2705837353412ad90055af3",
            "901da321bb4db7928befb698a9e35353d59d35368adb1d09b064b593fbcf7c71",
            "455f9dd6570530dd16befd78ce20f889c5559b35667b1dea4f36b2cb9a934863",
            "eec5e8a06c008829f5aa977ebc00f335b5e16f9173a9862a108d00001167cd45",
            "23659cb18871df2589673e77d9cd5fb09d98404ce6dd739150b0875c029abd1f",
            "88a2e4b3af3cc92abb872e370ad9c8def2bc936cf8802ccd0fdd941ffcddb82b",
            "e02e57c6ac46452406f0875b902de9e6e5ef4bd0d74694d872ad7806600f5188",
            "5e88ebb04b1707ede9a39060b3a7c22e0c72ee6949718729ec145087692b80e8",
        ),
    },
    "dc2eefd750653fe96b856789b279f2fe8b461cdf13fad7e39e9a89a03d38a2ed": {
        "application_number": "13/757675",
        "family_id": "48495278",
        "normalized_text_sha256": (
            "1501a3dce84f0b68734dbc8691f7e3bb6ddfb7127a9064be12a7a572ccaf8f9b"
        ),
        "page_count": 31,
        "sheet_count": 21,
        "blank_mirror_pages": frozenset({12}),
        "owner_count": 2,
        "relationship_binding_counts": {
            "continuation_parent_application": 0,
            "related_parent_application": 0,
            "parent_grant": 0,
            "prior_publication": 1,
        },
        "role_pages": {
            **{f"genius_four_six_optical_{index}": page - 1 for index, page in enumerate((5, 8, 11, 14, 17, 20), 1)},
            **{f"genius_four_six_asphere_{index}": page - 1 for index, page in enumerate((6, 9, 12, 15, 18, 21), 1)},
            "genius_four_six_comparison": 21,
        },
        "role_sheets": {
            **{f"genius_four_six_optical_{index}": sheet for index, sheet in enumerate((3, 6, 9, 12, 15, 18), 1)},
            **{f"genius_four_six_asphere_{index}": sheet for index, sheet in enumerate((4, 7, 10, 13, 16, 19), 1)},
            "genius_four_six_comparison": 20,
        },
        "page_image_sha256": (
            "ce6167c277276d09b859f0a40bcc4d53774c26199e16d7c80e5fe7851e2c6084",
            "b137bd70e57a6892256fe15e928c1c5093d1c7707149057e6fb41170fab4d349",
            "4c57a58f1d47785323636d75949d182d236358214f9dae0f81a3570d7f074503",
            "f554a92e4158368e1c6a673a11aa39f80a77e48cfa2971232e4c4894e8436a55",
            "9acd706cb1f504223c31f38683ac5e759cb468c7ce732fca8c910230859224b7",
            "85a85ad7702df5a54536627ce6f0badc0662c1f0ae1d41ca798bc26d5c238b66",
            "e67dd19c796eaf0ec57a2f59a7d50032761ad05bd3079e22b77075dcba71d5dc",
            "7b42e2fb609f4a65e7f688b029745a82c5733fd928361b220c937a2d18fccd7a",
            "b753340ff88a7cdf3ecd335d36c74d831fb292bc5c5197b9f9dc80f5031e9f84",
            "5015109f6564204450b473a56691680e0be25f1647f4fc54ed79853937d34c9e",
            "79375eca336a336f899f47e4c55fbe49258c0d62e3d730f13792dbfd3ff209aa",
            "59ea737b2084f8d98110b0796e2d77eb65fa7cf4100bf74ea8c8386a20bc6051",
            "4f9441b07e94768c788464a6bf529356bff91b650d0c40e28d7ed34aebbe6a31",
            "824f7aae24905e388a8dd5e8f345dd7e6128068e1ac8d42fe2d6c510c54a1cf0",
            "3e5d6bd21351ef01d2415df561b197335051ecbe3ab1e85bf8bdb39b3580ecbe",
            "25d252cce212da2a28e8b5631b75297891a34521aaa6619789bdfc518f5703ab",
            "4eb5017feebe79289ef1373c0f1780b3512543c4e49be34e19353a32a96d4650",
            "57cbae14699fd72b941d3eb750857d7eaf0a1b0d14b93d631cc8cc231630ca54",
            "8a5d453bd90d91a90a46874e781ad7082afba5e0815b092880940c934e0f7900",
            "78d4689c50bf90a39d822683365b3ffffe7d62ee227e520ce40ad68b93d18dce",
            "fc380b9c77ca06c8a7fa2ad9f1960b6f79a04fdec825b20e41bc9f44db5e9a34",
            "65dcc1c0c83c0fbd8bf87cc6415904a09cc818cee5caf79320934159a800aba7",
            "d17b2a9ab3eb2ef602bcbabaa325c19284480a5c1c6b3ed67e4f5d37e16557d9",
            "e7b8db441242e581597904874f902e9c585dc8583064562e19d554267d092ac4",
            "fd40fdc774729fa4d3b392376846d0a97400c4cd9f14876c20ccc6bde3e0fb1f",
            "8ebd1ad291064c05bf79dbd78f633614409f6883bb16785b77c8a808aebe27f7",
            "53ca619e47d14027306c2620352fcfa880ae4bf07ee7222b9c9fcb5bb7cb2cbf",
            "106163ee43aea4547361da1504155be803b49e5161f585037489d8b3bcd736da",
            "f74332749e71067c225105383e1841f8a09c7da07c6d0e02ad1716901e5e1ed0",
            "b66781143ddbd1beadaa11eac31fe078e760196a22ae6b33a410520bb274d51a",
            "ccedc9df824aead3068ed3fbd09b646c9bc86bae4e265909571a7aff5f5900f5",
        ),
    },
}
_GENIUS_FOUR_LENS_ELEVEN_OPTICAL_FIGURES = (2, 7, 11, 15, 19, 23, 27, 31, 35, 39, 43)
_GENIUS_FOUR_LENS_ELEVEN_ASPHERE_FIGURES = (4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44)
_GENIUS_FOUR_LENS_ELEVEN_REQUIRED_FIGURE_TEXT = tuple(
    marker
    for embodiment, (optical_figure, asphere_figure) in enumerate(
        zip(
            _GENIUS_FOUR_LENS_ELEVEN_OPTICAL_FIGURES,
            _GENIUS_FOUR_LENS_ELEVEN_ASPHERE_FIGURES,
            strict=True,
        ),
        start=1,
    )
    for marker in (
        f"FIG. {optical_figure} shows a table of optical data of each lens element "
        f"of the optical imaging lens according to embodiment {embodiment} of the invention",
        f"FIG. {asphere_figure} shows a table of aspherical data of the optical imaging lens "
        f"according to embodiment {embodiment} of the invention",
    )
)
_GENIUS_FOUR_LENS_ELEVEN_COMPARISON_MARKERS = (
    "FIG. 46 shows a comparison table",
    "all 11 example embodiments shown in FIGS. 1",
)
_GENIUS_FOUR_LENS_ELEVEN_PROFILE = "genius_four_lens_eleven_embodiment_census_v1"
_GENIUS_FOUR_LENS_ELEVEN_SOURCE_LAYOUTS: dict[str, dict[str, Any]] = {
    "0211f3fe1bdd3152ab6c57c25e4991603504980b37398c9ae5cbcb9812c43dea": {
        "page_count": 66,
        "drawing_page_offset": 1,
        "blank_mirror_pages": frozenset({6, 17, 21, 33, 45}),
    },
    "3b6a1046e050f84cd85e6e04efeee1a2ca96ff2450b1b810816733d7a3d03a73": {
        "page_count": 65,
        "drawing_page_offset": 1,
        "blank_mirror_pages": frozenset({48}),
    },
    "bdc8b8babf2e783d5c8bb49be17a1c79ff143aba871d0ac217edc6e63e8def6a": {
        "page_count": 66,
        "drawing_page_offset": 2,
        "blank_mirror_pages": frozenset({6, 7, 11, 19, 23, 27, 32, 50}),
    },
    "8b17a79c47cb8c9b589e62cba4097197485d1827ea7ed7147ba57da9f4ccd873": {
        "page_count": 65,
        "drawing_page_offset": 1,
        "blank_mirror_pages": frozenset({6, 10, 17, 30, 41, 42, 48}),
    },
}
_GENIUS_NINE_LENS_ELEVEN_ORDINALS = (
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "eighth",
    "ninth",
    "tenth",
    "eleventh",
)
_GENIUS_NINE_LENS_ELEVEN_OPTICAL_FIGURES = tuple(8 + 4 * index for index in range(11))
_GENIUS_NINE_LENS_ELEVEN_ASPHERE_FIGURES = tuple(9 + 4 * index for index in range(11))
_GENIUS_NINE_LENS_ELEVEN_REQUIRED_FIGURE_TEXT = tuple(
    marker
    for embodiment, (ordinal, optical_figure, asphere_figure) in enumerate(
        zip(
            _GENIUS_NINE_LENS_ELEVEN_ORDINALS,
            _GENIUS_NINE_LENS_ELEVEN_OPTICAL_FIGURES,
            _GENIUS_NINE_LENS_ELEVEN_ASPHERE_FIGURES,
            strict=True,
        ),
        start=1,
    )
    for marker in (
        (
            f"FIG. {optical_figure} depicts a table of optical data for each lens element "
            + (
                f"of {'an' if ordinal in {'eighth', 'eleventh'} else 'a'} {ordinal} "
                "embodiment of an optical imaging lens according to "
                if embodiment == 1 or embodiment >= 7
                else f"of the optical imaging lens of a {ordinal} embodiment of "
            )
            + "the present disclosure"
        ),
        f"FIG. {asphere_figure} depicts a table of aspherical data of "
        f"{'an' if ordinal in {'eighth', 'eleventh'} else 'a'} {ordinal} "
        "embodiment of the optical imaging lens according to the present disclosure",
    )
)
_GENIUS_NINE_LENS_ELEVEN_COMPARISON_MARKERS = (
    "FIGS. 50 A and 50 B depict tables for the values of",
    "of all eleven example embodiments",
)
_GENIUS_NINE_LENS_ELEVEN_PROFILE = "genius_nine_lens_eleven_embodiment_census_v1"
_GENIUS_EIGHT_LENS_FOURTEEN_ORDINALS = (
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "eighth",
    "ninth",
    "tenth",
    "eleventh",
    "twelfth",
    "thirteenth",
    "fourteenth",
)
_GENIUS_EIGHT_LENS_FOURTEEN_DESIGNATORS = (
    "1 ′",
    "2 ′",
    "3 ′",
    "4 ′",
    "5 ′",
    "6",
    "7",
    "8",
    "9",
    "10",
    "11 ′",
    "12 ′",
    "13 ′",
    "14 ′",
)
_GENIUS_EIGHT_LENS_FOURTEEN_OPTICAL_FIGURES = tuple(8 + 4 * index for index in range(14))
_GENIUS_EIGHT_LENS_FOURTEEN_ASPHERE_FIGURES = tuple(9 + 4 * index for index in range(14))
_GENIUS_EIGHT_LENS_FOURTEEN_REQUIRED_FIGURE_TEXT = tuple(
    marker
    for embodiment, (ordinal, designator, optical_figure, asphere_figure) in enumerate(
        zip(
            _GENIUS_EIGHT_LENS_FOURTEEN_ORDINALS,
            _GENIUS_EIGHT_LENS_FOURTEEN_DESIGNATORS,
            _GENIUS_EIGHT_LENS_FOURTEEN_OPTICAL_FIGURES,
            _GENIUS_EIGHT_LENS_FOURTEEN_ASPHERE_FIGURES,
            strict=True,
        ),
        start=1,
    )
    for marker in (
        f"FIG. {optical_figure} {'illustrates' if embodiment == 1 else 'shows'} an example "
        f"table of optical data of each lens element of the optical imaging lens {designator} "
        f"according to the {ordinal} example embodiment",
        f"FIG. {asphere_figure} {'depicts' if embodiment == 1 else 'shows'} an example table "
        f"of aspherical data of the optical imaging lens {designator} according to the "
        f"{ordinal} example embodiment",
    )
)
_GENIUS_EIGHT_LENS_FOURTEEN_COMPARISON_MARKERS = (
    "FIG. 62 A and FIG. 62 B are tables for the values of",
    "of all embodiments",
    "the fourteen embodiments",
)
_GENIUS_EIGHT_LENS_FOURTEEN_PROFILE = (
    "genius_eight_lens_fourteen_embodiment_census_v1"
)
_GENIUS_SEVEN_LENS_SEVEN_ORDINALS = (
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
)
_GENIUS_SEVEN_LENS_SEVEN_OPTICAL_FIGURES = tuple(
    20 + 2 * index for index in range(7)
)
_GENIUS_SEVEN_LENS_SEVEN_ASPHERE_FIGURES = tuple(
    21 + 2 * index for index in range(7)
)
_GENIUS_SEVEN_LENS_SEVEN_REQUIRED_FIGURE_TEXT = tuple(
    marker
    for ordinal, optical_figure, asphere_figure in zip(
        _GENIUS_SEVEN_LENS_SEVEN_ORDINALS,
        _GENIUS_SEVEN_LENS_SEVEN_OPTICAL_FIGURES,
        _GENIUS_SEVEN_LENS_SEVEN_ASPHERE_FIGURES,
        strict=True,
    )
    for marker in (
        f"FIG. {optical_figure} shows the optical data of the {ordinal} example "
        "of the optical imaging lens set.",
        f"FIG. {asphere_figure} shows the aspheric surface data of the {ordinal} example.",
    )
)
_GENIUS_SEVEN_LENS_SEVEN_COMPARISON_MARKERS = (
    "FIG. 34 shows some important ratios in the examples.",
    "FIG. 35 shows some important ratios in the examples.",
)
_GENIUS_SEVEN_LENS_SEVEN_SYSTEM_VALUES = (
    {"ttl_mm": 5.56, "f_number": 1.6239, "image_height_mm": 3.241, "hfov_deg": 38.0038},
    {"ttl_mm": 5.3991, "f_number": 1.6025, "image_height_mm": 3.238, "hfov_deg": 38.002},
    {"ttl_mm": 5.3665, "f_number": 1.6197, "image_height_mm": 2.42, "hfov_deg": 30.1264},
    {"ttl_mm": 5.3157, "f_number": 1.6115, "image_height_mm": 3.225, "hfov_deg": 37.9995},
    {"ttl_mm": 5.3343, "f_number": 1.6059, "image_height_mm": 3.237, "hfov_deg": 37.9981},
    {"ttl_mm": 5.0626, "f_number": 1.6014, "image_height_mm": 3.176, "hfov_deg": 37.9978},
    {"ttl_mm": 5.5733, "f_number": 1.611, "image_height_mm": 3.238, "hfov_deg": 37.9627},
)
_GENIUS_SEVEN_LENS_SEVEN_PROFILE = "genius_seven_lens_seven_example_census_v1"
_GENIUS_SEVEN_LENS_SEVEN_SOURCE_LAYOUTS: dict[str, dict[str, Any]] = {
    "7a3936c854f9d03ed76cc79656f9fbcb69946c78a3020c9b43708d5a9b9b615b": {
        "application_number": "18/743044",
        "family_id": "59199108",
        "normalized_text_sha256": (
            "a1f8dbbf0ff28ef241acc6a1097965b42193956b46974fb998bacd0831ce9897"
        ),
        "page_count": 36,
        "system_values": _GENIUS_SEVEN_LENS_SEVEN_SYSTEM_VALUES,
    },
    "1197f4ec4bb5df4a37e2b93c1bf5292aab4b2f27fdfede1e09e0d0a896807da8": {
        "application_number": "18/743044",
        "family_id": "59199108",
        "normalized_text_sha256": (
            "8d9964870318343219462cd3ad79b2d7b9666b5c059c52c29a758d50c194ecc1"
        ),
        "page_count": 36,
        "system_values": _GENIUS_SEVEN_LENS_SEVEN_SYSTEM_VALUES,
    },
}
_GENIUS_FOUR_LENS_NINE_OPTICAL_FIGURES = (8, 12, 16, 20, 24, 28, 32, 36, 40)
_GENIUS_FOUR_LENS_NINE_ASPHERE_FIGURES = (9, 13, 17, 21, 25, 29, 33, 37, 41)
_GENIUS_FOUR_LENS_NINE_REQUIRED_FIGURE_TEXT = tuple(
    marker
    for ordinal, optical_figure, asphere_figure in zip(
        ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth"),
        _GENIUS_FOUR_LENS_NINE_OPTICAL_FIGURES,
        _GENIUS_FOUR_LENS_NINE_ASPHERE_FIGURES,
        strict=True,
    )
    for marker in (
        f"FIG. {optical_figure} shows detailed optical data of the optical imaging lens of the "
        f"{ordinal} embodiment of the disclosure",
        f"FIG. {asphere_figure} shows aspheric parameters of the optical imaging lens of the "
        f"{ordinal} embodiment of the disclosure",
    )
)
_GENIUS_FOUR_LENS_NINE_COMPARISON_MARKERS = (
    "FIG. 42 and FIG. 43 show values of important parameters and their relational expressions "
    "of the optical imaging lenses of the first to fifth embodiments of the disclosure",
    "FIG. 44 and FIG. 45 show values of important parameters and their relational expressions "
    "of the optical imaging lenses of the sixth to ninth embodiments of the disclosure",
)
_GENIUS_FOUR_LENS_NINE_PROFILE = "genius_four_lens_nine_embodiment_census_v1"
_GENIUS_FOUR_LENS_EIGHT_ORDINALS = (
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "eighth",
)
_GENIUS_FOUR_LENS_EIGHT_OPTICAL_FIGURES = tuple(range(22, 38, 2))
_GENIUS_FOUR_LENS_EIGHT_ASPHERE_FIGURES = tuple(range(23, 38, 2))
_GENIUS_FOUR_LENS_EIGHT_REQUIRED_FIGURE_TEXT = tuple(
    marker
    for ordinal, optical_figure, asphere_figure in zip(
        _GENIUS_FOUR_LENS_EIGHT_ORDINALS,
        _GENIUS_FOUR_LENS_EIGHT_OPTICAL_FIGURES,
        _GENIUS_FOUR_LENS_EIGHT_ASPHERE_FIGURES,
        strict=True,
    )
    for marker in (
        f"FIG. {optical_figure} shows the optical data of the {ordinal} embodiment "
        "of the optical imaging lens.",
        f"FIG. {asphere_figure} shows the aspheric surface data of the {ordinal} "
        "embodiment.",
    )
)
_GENIUS_FOUR_LENS_EIGHT_COMPARISON_MARKER = (
    "FIG. 38 shows some important ratios in the embodiments."
)
_GENIUS_FOUR_LENS_EIGHT_SYSTEM_METADATA = (
    "EFL=17.619 mm; HFOV=11.161 degrees; TTL=21.995 mm; Fno=2.800; ImgH=3.528 mm.",
    "EFL=14.929 mm; HFOV=13.283 degrees; TTL=19.055 mm; Fno=2.800; ImgH=3.528 mm.",
    "EFL=14.625 mm; HFOV=13.486 degrees; TTL=19.966 mm; Fno=2.800; ImgH=3.528 mm.",
    "EFL=13.689 mm; HFOV=14.303 degrees; TTL=18.709 mm; Fno=2.800; ImgH=3.528 mm.",
    "EFL=14.238 mm; HFOV=13.708 degrees; TTL=19.025 mm; Fno=2.800; ImgH=3.525 mm.",
    "EFL=17.619 mm; HFOV=13.552 degrees; TTL=18.948 mm; Fno=2.800; ImgH-3.528 mm.",
    "EFL=11.763 mm; HFOV=16.199 degrees; TTL=14.935 mm; Fno=2.800; ImgH=3.528 mm.",
    "EFL=13.975 mm; HFOV=14.009 degrees; TTL=17.792 mm; Fno=2.800; ImgH=3.528 mm.",
)
_GENIUS_FOUR_LENS_EIGHT_PROFILE = "genius_four_lens_eight_embodiment_census_v1"
_GENIUS_FOUR_LENS_EIGHT_SOURCE_LAYOUTS: dict[str, dict[str, Any]] = {
    "0ec8d06ad327d41be5573d8b69fa6597d94c9f239eda657c5a050f3c121e61a3": {
        "normalized_text_sha256": (
            "236225514d4ae4f8c39602a177210b96d4f9da01fce6b58c18f78d90823677ce"
        ),
        "application_number": "19/034574",
        "family_id": "94801574",
    },
}
_GENIUS_SIX_LENS_FIVE_OPTICAL_FIGURES = (9, 13, 17, 21, 25)
_GENIUS_SIX_LENS_FIVE_ASPHERE_FIGURES = (10, 14, 18, 22, 26)
_GENIUS_SIX_LENS_FIVE_ORDINALS = ("first", "second", "third", "fourth", "fifth")
_GENIUS_SIX_LENS_FIVE_REQUIRED_FIGURE_TEXT = tuple(
    marker
    for ordinal, optical_figure, asphere_figure in zip(
        _GENIUS_SIX_LENS_FIVE_ORDINALS,
        _GENIUS_SIX_LENS_FIVE_OPTICAL_FIGURES,
        _GENIUS_SIX_LENS_FIVE_ASPHERE_FIGURES,
        strict=True,
    )
    for marker in (
        f"FIG. {optical_figure} shows detailed optical data of the optical lens assembly "
        f"according to the {ordinal} embodiment of the disclosure",
        f"FIG. {asphere_figure} shows aspheric parameters of the optical lens assembly "
        f"according to the {ordinal} embodiment of the disclosure",
    )
)
_GENIUS_SIX_LENS_FIVE_COMPARISON_MARKER = (
    "FIGS. 27 and 28 shows values of important parameters and relational expressions thereof "
    "of the optical lens assemblies according to the first to fifth embodiments of the disclosure"
)
_GENIUS_SIX_LENS_FIVE_PROFILE = "genius_six_lens_five_embodiment_census_v1"
_GENIUS_SIX_LENS_NINE_OPTICAL_FIGURES = (9, 13, 17, 21, 25, 29, 33, 37, 41)
_GENIUS_SIX_LENS_NINE_ASPHERE_FIGURES = (10, 14, 18, 22, 26, 30, 34, 38, 42)
_GENIUS_SIX_LENS_NINE_ORDINALS = (
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "eighth",
    "ninth",
)
_GENIUS_SIX_LENS_NINE_REQUIRED_FIGURE_TEXT = tuple(
    marker
    for ordinal, optical_figure, asphere_figure in zip(
        _GENIUS_SIX_LENS_NINE_ORDINALS,
        _GENIUS_SIX_LENS_NINE_OPTICAL_FIGURES,
        _GENIUS_SIX_LENS_NINE_ASPHERE_FIGURES,
        strict=True,
    )
    for marker in (
        f"FIG. {optical_figure} shows the detailed optical data of the optical lens assembly "
        f"according to the {ordinal} embodiment of the disclosure",
        f"FIG. {asphere_figure} shows the aspheric parameters of the optical lens assembly "
        f"according to the {ordinal} embodiment of the disclosure",
    )
)
_GENIUS_SIX_LENS_NINE_COMPARISON_MARKERS = (
    "FIG. 43 shows the values of important parameters of the optical lens assembly and their "
    "relational values according to the first to the fifth embodiments of the disclosure",
    "FIG. 44 shows the values of important parameters of the optical lens assembly and their "
    "relational values according to the sixth to the ninth embodiments of the disclosure",
)
_GENIUS_SIX_LENS_NINE_PROFILE = "genius_six_lens_nine_embodiment_census_v1"
_GENIUS_SIX_LENS_TEN_DUAL_FOCUS_ORDINALS = (
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "eighth",
    "ninth",
    "tenth",
)
_GENIUS_SIX_LENS_TEN_DUAL_FOCUS_OPTICAL_FIGURES = tuple(
    26 + 2 * index for index in range(10)
)
_GENIUS_SIX_LENS_TEN_DUAL_FOCUS_ASPHERE_FIGURES = tuple(
    27 + 2 * index for index in range(10)
)
_GENIUS_SIX_LENS_TEN_DUAL_FOCUS_REQUIRED_FIGURE_TEXT = tuple(
    (
        f"The optical data of the {ordinal} embodiment of the optical imaging lens"
        f"{' 1' if embodiment == 1 else ''} are shown in FIG. {optical_figure} while the "
        f"aspheric surface data are shown in FIG. {asphere_figure} ."
    )
    for embodiment, (ordinal, optical_figure, asphere_figure) in enumerate(
        zip(
            _GENIUS_SIX_LENS_TEN_DUAL_FOCUS_ORDINALS,
            _GENIUS_SIX_LENS_TEN_DUAL_FOCUS_OPTICAL_FIGURES,
            _GENIUS_SIX_LENS_TEN_DUAL_FOCUS_ASPHERE_FIGURES,
            strict=True,
        ),
        start=1,
    )
)
_GENIUS_SIX_LENS_TEN_DUAL_FOCUS_COMPARISON_MARKER = (
    "Some important ratios in each embodiment at the first focusing state or at the second "
    "focusing state are shown in FIG. 46 , in FIG. 47 , in FIG. 48 , and in FIG. 49 ."
)
_GENIUS_SIX_LENS_TEN_DUAL_FOCUS_PROFILE = (
    "genius_six_lens_ten_dual_focus_census_v1"
)
_GENIUS_SIX_LENS_NINE_THREE_COMPARISON_ORDINALS = (
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "eighth",
    "nineth",
)
_GENIUS_SIX_LENS_NINE_THREE_COMPARISON_REQUIRED_FIGURE_TEXT = tuple(
    marker
    for ordinal, optical_figure, asphere_figure in zip(
        _GENIUS_SIX_LENS_NINE_THREE_COMPARISON_ORDINALS,
        _GENIUS_SIX_LENS_NINE_OPTICAL_FIGURES,
        _GENIUS_SIX_LENS_NINE_ASPHERE_FIGURES,
        strict=True,
    )
    for marker in (
        f"FIG. {optical_figure} shows detailed optical data of the optical lens assembly "
        f"according to the {ordinal} embodiment of the disclosure",
        f"FIG. {asphere_figure} shows aspheric parameters of the optical lens assembly "
        f"according to the {ordinal} embodiment of the disclosure",
    )
)
_GENIUS_SIX_LENS_NINE_THREE_COMPARISON_MARKERS = (
    "FIG. 43 shows values of important parameters and relational expressions thereof of the "
    "optical lens assembly according to the first to third embodiments of the disclosure",
    "FIG. 44 shows values of important parameters and relational expressions thereof of the "
    "optical lens assembly according to the fourth to sixth embodiments of the disclosure",
    "FIG. 45 shows values of important parameters and relational expressions thereof of the "
    "optical lens assembly according to the seventh to nineth embodiments of the disclosure",
)
_GENIUS_SIX_LENS_NINE_THREE_COMPARISON_PROFILE = (
    "genius_six_lens_nine_three_comparison_census_v1"
)
_GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_REQUIRED_FIGURE_TEXT = tuple(
    marker
    for ordinal, optical_figure, asphere_figure in zip(
        _GENIUS_SIX_LENS_NINE_ORDINALS,
        _GENIUS_SIX_LENS_NINE_OPTICAL_FIGURES,
        _GENIUS_SIX_LENS_NINE_ASPHERE_FIGURES,
        strict=True,
    )
    for marker in (
        f"FIG. {optical_figure} illustrates "
        f"{'the ' if ordinal == 'ninth' else ''}detailed optical data of the optical lens "
        f"assembly according to the {ordinal} embodiment of the invention",
        f"FIG. {asphere_figure} illustrates "
        f"{'the ' if ordinal == 'ninth' else ''}aspheric parameters of the optical lens "
        f"assembly according to the {ordinal} embodiment of the invention",
    )
)
_GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_MARKERS = (
    "FIG. 43 to FIG. 46 illustrate all important parameters and numerical values of relational "
    "expressions for the optical lens element assemblies according to the first to ninth "
    "embodiments of the invention",
    "FIG. 43 and FIG. 45",
    "FIG. 44 and FIG. 46",
)
_GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_EXPECTED_COUNTS = (1, 5, 4)
_GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_PROFILE = (
    "genius_six_lens_nine_four_comparison_census_v1"
)
_GENIUS_OFFICIAL_ONLY_PROFILES = frozenset(
    {
        _GENIUS_SIX_LENS_FIVE_PROFILE,
        _GENIUS_SIX_LENS_NINE_PROFILE,
        _GENIUS_SIX_LENS_TEN_DUAL_FOCUS_PROFILE,
        _GENIUS_SIX_LENS_NINE_THREE_COMPARISON_PROFILE,
        _GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_PROFILE,
        _GENIUS_FOUR_LENS_NINE_PROFILE,
        _GENIUS_FOUR_LENS_EIGHT_PROFILE,
        _GENIUS_NINE_LENS_ELEVEN_PROFILE,
        _GENIUS_EIGHT_LENS_FOURTEEN_PROFILE,
        _GENIUS_SEVEN_LENS_SEVEN_PROFILE,
        _CIRCLE_OPTICS_SEVEN_LENS_PROFILE,
    }
)
_SYSTEM_VALUE_PATTERN_TEMPLATE = (
    r"\b{label}\s*(?:=|:|is(?:\s+set\s+to)?)\s*"
    r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:E[-+]?\d+)?"
)
_PDF_HEADER = b"%PDF-"


class PatentPdfRecoveryError(RuntimeError):
    """Raised when a PDF/OCR linkage or extraction invariant is not proven."""


@dataclass(frozen=True)
class PatentPdfOcrRecovery:
    publication_id: str
    official_pdf: bytes
    official_pdf_url: str
    mirror_pdf: bytes | None
    mirror_pdf_url: str | None
    parser_input: bytes
    page_count: int
    page_image_sha256: tuple[str, ...]
    key_page_numbers: tuple[int, ...]
    pypdf_version: str
    rapidocr_version: str


@dataclass(frozen=True)
class PatentPdfCachedSources:
    """Immutable PDF bytes selected by the patent-lake source pin."""

    official_pdf: bytes
    official_pdf_url: str
    mirror_pdf: bytes | None
    mirror_pdf_url: str | None


def _normalized_html_text(raw_html: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw_html))
    return re.sub(r"\s+", " ", text).strip()


def _ability_layout_profile(raw_html: str) -> str | None:
    """Return the exact source-proven Ability drawing-table profile."""

    text = _normalized_html_text(raw_html)
    digest = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()
    if digest in _SNAP_SIX_LENS_TWO_DESIGN_SOURCE_LAYOUTS and all(
        marker in text for marker in _SNAP_SIX_LENS_TWO_DESIGN_REQUIRED_TEXT
    ):
        return _SNAP_SIX_LENS_TWO_DESIGN_PROFILE
    if digest in _CIRCLE_OPTICS_SEVEN_LENS_SOURCE_LAYOUTS and all(
        marker in text for marker in _CIRCLE_OPTICS_SEVEN_LENS_REQUIRED_TEXT
    ):
        return _CIRCLE_OPTICS_SEVEN_LENS_PROFILE
    if digest in _KODAK_LOW_STRESS_SOURCE_LAYOUTS and all(
        marker in text for marker in _KODAK_LOW_STRESS_REQUIRED_TEXT
    ):
        return _KODAK_LOW_STRESS_TWO_LENS_PROFILE
    if digest in _ABILITY_THREE_FIVE_LENS_SOURCE_LAYOUTS and all(
        re.search(pattern, text, flags=re.IGNORECASE) is not None
        for pattern in _ABILITY_THREE_FIVE_LENS_BINDING_PATTERNS.values()
    ):
        return _ABILITY_THREE_FIVE_LENS_PROFILE
    if digest in _ABILITY_FOUR_WIDE_ANGLE_SOURCE_LAYOUTS and all(
        re.search(pattern, text, flags=re.IGNORECASE) is not None
        for pattern in _ABILITY_FOUR_WIDE_ANGLE_BINDING_PATTERNS.values()
    ):
        return _ABILITY_FOUR_WIDE_ANGLE_PROFILE
    if all(marker in text for marker in _ABILITY_REQUIRED_FIGURE_TEXT):
        return "ability_two_lens_prescriptions_v1"
    if all(marker in text for marker in _ABILITY_EIGHT_LENS_REQUIRED_FIGURE_TEXT):
        return _ABILITY_EIGHT_LENS_PROFILE
    if all(marker in text for marker in _ABILITY_THREE_LENS_REQUIRED_FIGURE_TEXT):
        return _ABILITY_THREE_LENS_PROFILE
    if all(marker in text for marker in _ABILITY_TWO_FIVE_LENS_REQUIRED_FIGURE_TEXT):
        return _ABILITY_TWO_FIVE_LENS_PROFILE
    if all(marker in text for marker in _ABILITY_TWO_NINE_LENS_REQUIRED_FIGURE_TEXT):
        return _ABILITY_TWO_NINE_LENS_PROFILE
    if all(marker in text for marker in _ABILITY_FOUR_EIGHT_LENS_REQUIRED_FIGURE_TEXT):
        return _ABILITY_FOUR_EIGHT_LENS_PROFILE
    if digest in _ABILITY_FIVE_THREE_LENS_SOURCE_LAYOUTS and all(
        marker in text for marker in _ABILITY_FIVE_THREE_LENS_REQUIRED_FIGURE_TEXT
    ):
        return _ABILITY_FIVE_THREE_LENS_PROFILE
    if digest in _AAC_TWO_THREE_LENS_SOURCE_LAYOUTS and all(
        marker in text for marker in _AAC_TWO_THREE_LENS_REQUIRED_FIGURE_TEXT
    ):
        return _AAC_TWO_THREE_LENS_PROFILE
    if all(marker in text for marker in _LARGAN_THREE_FIVE_LENS_REQUIRED_FIGURE_TEXT):
        return _LARGAN_THREE_FIVE_LENS_PROFILE
    if all(marker in text for marker in _ABILITY_ZOOM_TWO_STATE_REQUIRED_FIGURE_TEXT):
        return _ABILITY_ZOOM_TWO_STATE_PROFILE
    if (
        digest in _GENIUS_FOUR_LENS_SIX_SOURCE_LAYOUTS
        and all(marker in text for marker in _GENIUS_FOUR_LENS_SIX_REQUIRED_FIGURE_TEXT)
        and text.count(_GENIUS_FOUR_LENS_SIX_COMPARISON_MARKER) == 1
        and all(marker in text for marker in _GENIUS_FOUR_LENS_SIX_DEVICE_MARKERS)
    ):
        return _GENIUS_FOUR_LENS_SIX_PROFILE
    if all(marker in text for marker in _GENIUS_FOUR_LENS_ELEVEN_REQUIRED_FIGURE_TEXT) and all(
        marker in text for marker in _GENIUS_FOUR_LENS_ELEVEN_COMPARISON_MARKERS
    ):
        return _GENIUS_FOUR_LENS_ELEVEN_PROFILE
    if all(
        marker in text for marker in _GENIUS_NINE_LENS_ELEVEN_REQUIRED_FIGURE_TEXT
    ) and all(marker in text for marker in _GENIUS_NINE_LENS_ELEVEN_COMPARISON_MARKERS):
        return _GENIUS_NINE_LENS_ELEVEN_PROFILE
    if all(
        marker in text for marker in _GENIUS_EIGHT_LENS_FOURTEEN_REQUIRED_FIGURE_TEXT
    ) and all(
        marker in text for marker in _GENIUS_EIGHT_LENS_FOURTEEN_COMPARISON_MARKERS
    ):
        return _GENIUS_EIGHT_LENS_FOURTEEN_PROFILE
    if all(
        marker in text for marker in _GENIUS_SEVEN_LENS_SEVEN_REQUIRED_FIGURE_TEXT
    ) and all(
        marker in text for marker in _GENIUS_SEVEN_LENS_SEVEN_COMPARISON_MARKERS
    ):
        return _GENIUS_SEVEN_LENS_SEVEN_PROFILE
    if all(marker in text for marker in _GENIUS_FOUR_LENS_NINE_REQUIRED_FIGURE_TEXT) and all(
        marker in text for marker in _GENIUS_FOUR_LENS_NINE_COMPARISON_MARKERS
    ):
        return _GENIUS_FOUR_LENS_NINE_PROFILE
    if (
        digest in _GENIUS_FOUR_LENS_EIGHT_SOURCE_LAYOUTS
        and all(marker in text for marker in _GENIUS_FOUR_LENS_EIGHT_REQUIRED_FIGURE_TEXT)
        and _GENIUS_FOUR_LENS_EIGHT_COMPARISON_MARKER in text
        and all(marker in text for marker in _GENIUS_FOUR_LENS_EIGHT_SYSTEM_METADATA)
    ):
        return _GENIUS_FOUR_LENS_EIGHT_PROFILE
    if all(marker in text for marker in _GENIUS_SIX_LENS_FIVE_REQUIRED_FIGURE_TEXT) and (
        _GENIUS_SIX_LENS_FIVE_COMPARISON_MARKER in text
    ):
        return _GENIUS_SIX_LENS_FIVE_PROFILE
    if all(marker in text for marker in _GENIUS_SIX_LENS_NINE_REQUIRED_FIGURE_TEXT) and all(
        marker in text for marker in _GENIUS_SIX_LENS_NINE_COMPARISON_MARKERS
    ):
        return _GENIUS_SIX_LENS_NINE_PROFILE
    if all(
        marker in text for marker in _GENIUS_SIX_LENS_TEN_DUAL_FOCUS_REQUIRED_FIGURE_TEXT
    ) and text.count(_GENIUS_SIX_LENS_TEN_DUAL_FOCUS_COMPARISON_MARKER) == 1:
        return _GENIUS_SIX_LENS_TEN_DUAL_FOCUS_PROFILE
    if all(
        marker in text
        for marker in _GENIUS_SIX_LENS_NINE_THREE_COMPARISON_REQUIRED_FIGURE_TEXT
    ) and all(marker in text for marker in _GENIUS_SIX_LENS_NINE_THREE_COMPARISON_MARKERS):
        return _GENIUS_SIX_LENS_NINE_THREE_COMPARISON_PROFILE
    if all(
        marker in text for marker in _GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_REQUIRED_FIGURE_TEXT
    ) and all(
        text.count(marker) == expected
        for marker, expected in zip(
            _GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_MARKERS,
            _GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_EXPECTED_COUNTS,
            strict=True,
        )
    ):
        return _GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_PROFILE
    return None


def ability_drawing_tables_declared(raw_html: str) -> bool:
    """Return whether official text declares a supported image-table layout."""

    return _ability_layout_profile(raw_html) is not None


def _ability_eight_lens_source_facts(raw_html: str) -> dict[str, Any]:
    """Measure the exact official-text facts needed for a terminal outcome."""

    text = _normalized_html_text(raw_html)
    assignments = {
        label: len(
            re.findall(
                _SYSTEM_VALUE_PATTERN_TEMPLATE.format(label=re.escape(label)),
                text,
                flags=re.IGNORECASE,
            )
        )
        for label in ("F", "FNO", "FOV")
    }
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "surface_figure_binding_count": text.count(
            _ABILITY_EIGHT_LENS_REQUIRED_FIGURE_TEXT[0]
        ),
        "asphere_figure_binding_count": text.count(
            _ABILITY_EIGHT_LENS_REQUIRED_FIGURE_TEXT[1]
        ),
        "fno_definition_count": text.count(
            _ABILITY_EIGHT_LENS_REQUIRED_FIGURE_TEXT[2]
        ),
        "fov_definition_count": text.count(
            _ABILITY_EIGHT_LENS_REQUIRED_FIGURE_TEXT[3]
        ),
        "numeric_system_value_assignment_counts": assignments,
    }


def _ability_three_lens_source_facts(raw_html: str) -> dict[str, Any]:
    """Measure the official figure bindings for the three-prescription layout."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker.split(" lists", maxsplit=1)[0]: text.count(marker)
            for marker in _ABILITY_THREE_LENS_REQUIRED_FIGURE_TEXT
        },
    }


def _ability_two_five_lens_source_facts(raw_html: str) -> dict[str, Any]:
    """Measure the official bindings for two disclosed five-lens prescriptions."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker.split(" shows", maxsplit=1)[0]: text.count(marker)
            for marker in _ABILITY_TWO_FIVE_LENS_REQUIRED_FIGURE_TEXT
        },
    }


def _ability_two_nine_lens_source_facts(raw_html: str) -> dict[str, Any]:
    """Measure figure bindings and the absence of any F-number label."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker.split(" lists", maxsplit=1)[0]: text.count(marker)
            for marker in _ABILITY_TWO_NINE_LENS_REQUIRED_FIGURE_TEXT
        },
        "f_number_label_counts": {
            "FNO": len(re.findall(r"\bFNO\b", text, flags=re.IGNORECASE)),
            "F-number": len(
                re.findall(r"\bF\s*[- ]?number\b", text, flags=re.IGNORECASE)
            ),
            "F/#": len(re.findall(r"\bF\s*/\s*#\b", text, flags=re.IGNORECASE)),
        },
    }


def _ability_four_eight_lens_source_facts(raw_html: str) -> dict[str, Any]:
    """Measure four prescription bindings and the absence of F-number labels."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker.split(" lists", maxsplit=1)[0]: text.count(marker)
            for marker in _ABILITY_FOUR_EIGHT_LENS_REQUIRED_FIGURE_TEXT
        },
        "f_number_label_counts": {
            "FNO": len(re.findall(r"\bFNO\b", text, flags=re.IGNORECASE)),
            "F-number": len(
                re.findall(r"\bF\s*[- ]?number\b", text, flags=re.IGNORECASE)
            ),
            "F/#": len(re.findall(r"\bF\s*/\s*#\b", text, flags=re.IGNORECASE)),
        },
    }


def ability_five_three_lens_source_layout_for_sha256(
    digest: str,
) -> dict[str, Any]:
    """Return the source-locked five-prescription PDF layout."""

    layout = _ABILITY_FIVE_THREE_LENS_SOURCE_LAYOUTS.get(digest)
    if layout is None:
        raise PatentPdfRecoveryError(
            "Ability five-three-lens official HTML is not source-locked"
        )
    return {**layout, "role_pages": dict(_ABILITY_FIVE_THREE_LENS_ROLE_PAGES)}


def _ability_five_three_lens_source_layout(raw_html: str) -> dict[str, Any]:
    digest = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()
    return ability_five_three_lens_source_layout_for_sha256(digest)


def _ability_five_three_lens_source_facts(raw_html: str) -> dict[str, Any]:
    """Bind five image prescriptions and prove their F-number is unpublished."""

    text = _normalized_html_text(raw_html)
    digest = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()
    layout = ability_five_three_lens_source_layout_for_sha256(digest)
    normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if normalized_digest != layout["normalized_text_sha256"]:
        raise PatentPdfRecoveryError(
            "Ability five-three-lens normalized official HTML hash changed"
        )

    number = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
    embodiment_values: dict[str, dict[str, float]] = {}
    embodiment_detail_counts: dict[str, int] = {}
    for ordinal in _ABILITY_FIVE_THREE_LENS_ORDINALS:
        detail_pattern = re.compile(
            rf"more detailed specification of (?:the|a) {ordinal} embodiment.*?"
            rf"is as follows:\s*(?P<body>.*?)(?=\[\d{{4}}\]|\(\d+\))",
            flags=re.IGNORECASE,
        )
        details = list(detail_pattern.finditer(text))
        embodiment_detail_counts[ordinal] = len(details)
        if len(details) != 1:
            raise PatentPdfRecoveryError(
                f"Ability five-three-lens {ordinal} embodiment detail count changed"
            )
        body = details[0].group("body")
        values: dict[str, float] = {}
        for label, pattern in {
            "entrance_pupil_diameter_mm": rf"\bEPD\s*=\s*({number})",
            "focal_length_mm": rf"(?<![A-Za-z0-9])f\s*=\s*({number})",
            "full_field_of_view_deg": rf"\bFOV\s*=\s*({number})",
        }.items():
            matches = re.findall(pattern, body, flags=re.IGNORECASE)
            if len(matches) != 1:
                raise PatentPdfRecoveryError(
                    f"Ability five-three-lens {ordinal} {label} count changed"
                )
            values[label] = float(matches[0])
        embodiment_values[ordinal] = values

    return {
        "primary_html_sha256": digest,
        "normalized_text_sha256": normalized_digest,
        "family_id": "55525612",
        "application_number": layout["application_number"],
        "figure_binding_counts": {
            marker.split(" shows", maxsplit=1)[0]: text.count(marker)
            for marker in _ABILITY_FIVE_THREE_LENS_REQUIRED_FIGURE_TEXT
        },
        "embodiment_detail_counts": embodiment_detail_counts,
        "embodiment_system_values": embodiment_values,
        "f_number_label_counts": {
            "FNO": len(re.findall(r"\bFNO\b", text, flags=re.IGNORECASE)),
            "F-number": len(
                re.findall(r"\bF\s*[- ]?number\b", text, flags=re.IGNORECASE)
            ),
            "F/#": len(re.findall(r"\bF\s*/\s*#\b", text, flags=re.IGNORECASE)),
        },
    }


def _aac_two_three_lens_source_layout(raw_html: str) -> dict[str, Any]:
    digest = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()
    layout = _AAC_TWO_THREE_LENS_SOURCE_LAYOUTS.get(digest)
    if layout is None:
        raise PatentPdfRecoveryError(
            "AAC two-three-lens official HTML is not source-locked"
        )
    return {**layout, "role_pages": dict(_AAC_TWO_THREE_LENS_ROLE_PAGES)}


def _aac_two_three_lens_source_facts(raw_html: str) -> dict[str, Any]:
    """Bind two complete prescriptions and prove system field is unpublished."""

    text = _normalized_html_text(raw_html)
    layout = _aac_two_three_lens_source_layout(raw_html)
    normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if normalized_digest != layout["normalized_text_sha256"]:
        raise PatentPdfRecoveryError(
            "AAC two-three-lens normalized official HTML hash changed"
        )

    table_pattern = re.compile(
        r"\bTABLE-US-(?P<anchor>\d{5})\s+TABLE\s+(?P<number>\d+)\s+",
        flags=re.IGNORECASE,
    )
    matches = list(table_pattern.finditer(text))
    if [(match.group("anchor"), int(match.group("number"))) for match in matches] != [
        (f"{number:05d}", number) for number in range(1, 6)
    ]:
        raise PatentPdfRecoveryError("AAC two-three-lens table denominator changed")
    table_blocks = [
        text[
            match.start() : matches[index + 1].start()
            if index + 1 < len(matches)
            else len(text)
        ]
        for index, match in enumerate(matches)
    ]
    table_digests = tuple(
        hashlib.sha256(block.encode("utf-8")).hexdigest() for block in table_blocks
    )
    if table_digests != layout["table_block_sha256"]:
        raise PatentPdfRecoveryError("AAC two-three-lens table content changed")

    number = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
    system_values: dict[str, dict[str, float]] = {}
    for embodiment, table_number in ((1, 1), (2, 3)):
        header = re.search(
            rf"\ATABLE-US-\d{{5}}\s+TABLE\s+{table_number}\s+Embodiment\s+"
            rf"{embodiment}\s+f\s*=\s*(?P<f>{number})\s*mm\s*,\s*"
            rf"Fno\s*=\s*(?P<fno>{number})\s*,\s*DOF"
            rf"(?:\s*\(depth\s+of\s+feild\))?\s*=\s*(?P<dof>{number})°",
            table_blocks[table_number - 1],
            flags=re.IGNORECASE,
        )
        if header is None:
            raise PatentPdfRecoveryError(
                f"AAC two-three-lens embodiment {embodiment} system header changed"
            )
        system_values[str(embodiment)] = {
            "focal_length_mm": float(header.group("f")),
            "f_number": float(header.group("fno")),
            "published_dof_deg": float(header.group("dof")),
        }

    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "normalized_text_sha256": normalized_digest,
        "family_id": "53345880",
        "application_number": layout["application_number"],
        "figure_binding_counts": {
            f"FIG. {number}": text.count(marker)
            for number, marker in enumerate(
                _AAC_TWO_THREE_LENS_REQUIRED_FIGURE_TEXT,
                start=1,
            )
        },
        "table_numbers": [1, 2, 3, 4, 5],
        "table_block_sha256": list(table_digests),
        "embodiment_table_bindings": {
            "1": {"surface_table": 1, "asphere_table": 2},
            "2": {"surface_table": 3, "asphere_table": 4},
        },
        "embodiment_system_values": system_values,
        "dof_label_count": len(re.findall(r"\bDOF\b", text, re.IGNORECASE)),
        "dof_expansion_count": len(
            re.findall(r"DOF\s*\(depth\s+of\s+feild\)", text, re.IGNORECASE)
        ),
        "system_field_label_counts": {
            "FOV": len(re.findall(r"\bFOV\b", text, re.IGNORECASE)),
            "HFOV": len(re.findall(r"\bHFOV\b", text, re.IGNORECASE)),
            "field of view": len(
                re.findall(r"\bfield\s+of\s+view\b", text, re.IGNORECASE)
            ),
            "angle of view": len(
                re.findall(r"\bangle\s+of\s+view\b", text, re.IGNORECASE)
            ),
        },
    }


def _largan_three_five_lens_source_facts(raw_html: str) -> dict[str, Any]:
    """Measure exact official bindings for three Largan five-lens prescriptions."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker.split(" is TABLE", maxsplit=1)[0]: text.count(marker)
            for marker in _LARGAN_THREE_FIVE_LENS_REQUIRED_FIGURE_TEXT
        },
    }


def _ability_zoom_two_state_source_facts(raw_html: str) -> dict[str, Any]:
    """Measure exact bindings for one telescopic and one wide-angle prescription."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker.split(" lists", maxsplit=1)[0]: text.count(marker)
            for marker in _ABILITY_ZOOM_TWO_STATE_REQUIRED_FIGURE_TEXT
        },
    }


def _snap_six_lens_two_design_source_layout(raw_html: str) -> dict[str, Any]:
    digest = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()
    layout = _SNAP_SIX_LENS_TWO_DESIGN_SOURCE_LAYOUTS.get(digest)
    if layout is None:
        raise PatentPdfRecoveryError(
            "Snap six-lens two-design official HTML is not source-locked"
        )
    return layout


def _snap_six_lens_two_design_source_facts(raw_html: str) -> dict[str, Any]:
    """Bind both prescriptions, claim-style examples, and the device wrapper."""

    text = _normalized_html_text(raw_html)
    layout = _snap_six_lens_two_design_source_layout(raw_html)
    normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if normalized_digest != layout["normalized_text_sha256"]:
        raise PatentPdfRecoveryError(
            "Snap six-lens two-design normalized official HTML hash changed"
        )
    required_counts = {
        marker: text.count(marker)
        for marker in _SNAP_SIX_LENS_TWO_DESIGN_REQUIRED_TEXT
    }
    expected_counts = {
        marker: 2 if marker.startswith("FIGS.") else 1
        for marker in _SNAP_SIX_LENS_TWO_DESIGN_REQUIRED_TEXT
    }
    if required_counts != expected_counts:
        raise PatentPdfRecoveryError(
            "Snap six-lens two-design required source-text counts changed"
        )
    example_pairs = tuple(
        (int(number), int(paragraph))
        for number, paragraph in re.findall(
            r"\bEXAMPLE\s+(\d+)\s+\((\d+)\)",
            text,
            flags=re.IGNORECASE,
        )
    )
    if example_pairs != tuple(zip(range(1, 38), range(51, 88), strict=True)):
        raise PatentPdfRecoveryError(
            "Snap six-lens two-design 37-example denominator changed"
        )
    independent_example_numbers = tuple(
        int(number)
        for number, _paragraph in re.findall(
            r"\bEXAMPLE\s+(\d+)\s+\((\d+)\)\s+"
            r"(?:An imaging lens assembly|A mobile device)",
            text,
            flags=re.IGNORECASE,
        )
    )
    if independent_example_numbers != (1, 10, 19, 28, 37):
        raise PatentPdfRecoveryError(
            "Snap six-lens two-design independent example anchors changed"
        )
    claims_text = text[text.rfind("Claims ") :]
    claim_numbers = tuple(
        int(number)
        for number in re.findall(
            r"(?:^|\s)(\d{1,2})\.\s+(?:An|The|A)\s+"
            r"(?:imaging lens assembly|mobile device)",
            claims_text,
            flags=re.IGNORECASE,
        )
    )
    if claim_numbers != tuple(range(1, 19)):
        raise PatentPdfRecoveryError(
            "Snap six-lens two-design 18-claim denominator changed"
        )
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "normalized_text_sha256": normalized_digest,
        "family_id": "61244801",
        "application_number": layout["application_number"],
        "pct_application": "PCT/US2018/017252",
        "pct_publication": "WO2018/148301",
        "prior_us_publication": "US 20200096726 A1",
        "provisional_application": "US 62455983",
        "required_text_counts": required_counts,
        "paragraph_ranges": {
            "priority_background_summary": [1, 6],
            "brief_description": [1, 7],
            "detailed_description": [8, 87],
            "claims": [1, 18],
        },
        "figure_numbers": list(range(1, 9)),
        "drawing_sheet_count": 8,
        "formal_html_table_count": 0,
        "sample_design_count": 2,
        "source_declared_example_numbers": list(range(1, 38)),
        "source_declared_example_paragraph_numbers": list(range(51, 88)),
        "independent_claim_style_example_numbers": [1, 10, 19, 28, 37],
        "dependent_claim_style_example_numbers": [
            number for number in range(1, 38) if number not in {1, 10, 19, 28, 37}
        ],
        "claim_numbers": list(range(1, 19)),
        "ledger_item_mapping": {
            "sample_design_1": {
                "item_number": 1,
                "lens_element_count": 5,
                "claim_style_examples": [19, 36],
            },
            "sample_design_2": {
                "item_number": 2,
                "lens_element_count": 6,
                "claim_style_examples": [1, 18],
            },
            "mobile_device_wrapper": {
                "item_number": 3,
                "claim_style_examples": [37, 37],
            },
        },
        "design_1_lens_element_count": 5,
        "design_2_lens_element_count": 6,
        "design_1_direct_system_metadata_present": False,
        "design_2_metadata": {
            "effective_focal_length_mm": 1.57,
            "assembly_length_mm": 6.71,
            "diagonal_field_of_view_deg": 115.0,
            "image_circle_field_of_view_deg": 120.0,
            "f_number": 2.4,
            "image_height_mm": 1.98,
        },
    }


def circle_optics_seven_lens_source_layout_for_sha256(
    digest: str,
) -> dict[str, Any]:
    """Return the source-locked layout for one Circle Optics publication."""

    layout = _CIRCLE_OPTICS_SEVEN_LENS_SOURCE_LAYOUTS.get(digest)
    if layout is None:
        raise PatentPdfRecoveryError(
            "Circle Optics seven-lens official HTML is not source-locked"
        )
    return layout


def _circle_optics_seven_lens_source_layout(raw_html: str) -> dict[str, Any]:
    digest = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()
    return circle_optics_seven_lens_source_layout_for_sha256(digest)


def _circle_optics_seven_lens_source_facts(raw_html: str) -> dict[str, Any]:
    """Bind the source text which describes the image-only seven-lens tables."""

    text = _normalized_html_text(raw_html)
    layout = _circle_optics_seven_lens_source_layout(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "family_id": "74060373",
        "application_number": layout["application_number"],
        "required_text_counts": {
            marker: text.count(marker)
            for marker in _CIRCLE_OPTICS_SEVEN_LENS_REQUIRED_TEXT
        },
        "lens_element_count": 7,
        "aspheric_lens_element_count": 3,
        "f_number": 2.0,
        "nominal_focal_length_mm": 2.57,
        "aperture_stop_diameter_mm": 1.42,
        "track_length_mm": 50.0,
        "image_width_mm": 3.9,
        "design_wavelengths_nm": [450, 587, 656],
    }


def kodak_low_stress_source_layout_for_sha256(digest: str) -> dict[str, Any]:
    """Return the source-locked FIG. 14A/14B layout for one publication."""

    layout = _KODAK_LOW_STRESS_SOURCE_LAYOUTS.get(digest)
    if layout is None:
        raise PatentPdfRecoveryError(
            "Kodak low-stress imaging-lens official HTML is not source-locked"
        )
    return layout


def _kodak_low_stress_source_layout(raw_html: str) -> dict[str, Any]:
    digest = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()
    return kodak_low_stress_source_layout_for_sha256(digest)


def _kodak_low_stress_source_facts(raw_html: str) -> dict[str, Any]:
    """Bind published prescriptions and prove their system metadata is absent."""

    text = _normalized_html_text(raw_html)
    digest = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()
    layout = kodak_low_stress_source_layout_for_sha256(digest)
    normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if normalized_digest != layout["normalized_text_sha256"]:
        raise PatentPdfRecoveryError(
            "Kodak low-stress normalized official HTML hash changed"
        )
    assignments = {
        label: len(
            re.findall(
                _SYSTEM_VALUE_PATTERN_TEMPLATE.format(label=re.escape(label)),
                text,
                flags=re.IGNORECASE,
            )
        )
        for label in ("F", "FNO", "FOV", "HFOV", "EFL")
    }
    return {
        "primary_html_sha256": digest,
        "normalized_text_sha256": normalized_digest,
        "family_id": "44121309",
        "application_number": layout["application_number"],
        "required_text_counts": {
            marker: text.count(marker) for marker in _KODAK_LOW_STRESS_REQUIRED_TEXT
        },
        "f_number_context_counts": {
            marker: text.count(marker) for marker in _KODAK_LOW_STRESS_F_NUMBER_CONTEXTS
        },
        "numeric_system_value_assignment_counts": assignments,
        "effective_focal_length_count": len(
            re.findall(r"\beffective focal length\b", text, flags=re.IGNORECASE)
        ),
        "focal_length_count": len(
            re.findall(r"\bfocal length\b", text, flags=re.IGNORECASE)
        ),
        "field_of_view_count": len(
            re.findall(r"\bfield of view\b", text, flags=re.IGNORECASE)
        ),
        "prescription_count": len(
            re.findall(r"\bprescription\b", text, flags=re.IGNORECASE)
        ),
    }


def genius_four_lens_six_source_layout_for_sha256(digest: str) -> dict[str, Any]:
    """Return the source-locked six-embodiment official PDF layout."""

    layout = _GENIUS_FOUR_LENS_SIX_SOURCE_LAYOUTS.get(digest)
    if layout is None:
        raise PatentPdfRecoveryError(
            "Genius four-lens six-embodiment official HTML is not source-locked"
        )
    return layout


def _genius_four_lens_six_source_layout(raw_html: str) -> dict[str, Any]:
    digest = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()
    layout = genius_four_lens_six_source_layout_for_sha256(digest)
    normalized_digest = hashlib.sha256(
        _normalized_html_text(raw_html).encode("utf-8")
    ).hexdigest()
    if normalized_digest != layout["normalized_text_sha256"]:
        raise PatentPdfRecoveryError(
            "Genius four-lens six-embodiment normalized official HTML hash changed"
        )
    return layout


def _genius_four_lens_six_source_facts(raw_html: str) -> dict[str, Any]:
    """Bind six raster table pairs, comparison data, lineage, and all 28 figures."""

    text = _normalized_html_text(raw_html)
    digest = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()
    layout = _genius_four_lens_six_source_layout(raw_html)
    brief_start = text.find("BRIEF DESCRIPTION OF THE DRAWINGS")
    brief_end = text.find("DETAILED DESCRIPTION OF THE INVENTION", brief_start)
    if brief_start < 0 or brief_end < 0:
        raise PatentPdfRecoveryError(
            "Genius four-lens six-embodiment drawing denominator is absent"
        )
    brief_text = text[brief_start:brief_end]
    declared_figures = sorted(
        {
            int(match.group(1))
            for match in re.finditer(r"\bFIGS?\.\s*(\d+)", brief_text)
        }
    )
    relationship_binding_counts = {
        "continuation_parent_application": len(
            re.findall(
                r"continuation of U\.S\. patent application Ser\. No\. 13/757,675",
                text,
                flags=re.IGNORECASE,
            )
        ),
        "related_parent_application": text.count(
            "parent US continuation 13757675 20130201"
        ),
        "parent_grant": text.count("parent-grant-document US 8976467"),
        "prior_publication": text.count("US 20140071340 A1"),
    }
    priority_binding_counts = {
        "CN201210328571.9": len(
            re.findall(r"201210328571\.9|2012 1 0328571", text)
        ),
        "CN201210437198.0": len(
            re.findall(r"201210437198\.0|2012 1 0437198", text)
        ),
    }
    return {
        "primary_html_sha256": digest,
        "normalized_text_sha256": layout["normalized_text_sha256"],
        "family_id": layout["family_id"],
        "application_number": layout["application_number"],
        "title_count": len(
            re.findall(
                r"Mobile device and optical imaging lens thereof",
                text,
                flags=re.IGNORECASE,
            )
        ),
        "owner_count": text.count("Genius Electronic Optical Co., Ltd."),
        "priority_binding_counts": priority_binding_counts,
        "relationship_binding_counts": relationship_binding_counts,
        "prescription_count": 6,
        "lens_element_count": 4,
        "figure_binding_counts": {
            marker: text.count(marker)
            for marker in _GENIUS_FOUR_LENS_SIX_REQUIRED_FIGURE_TEXT
        },
        "comparison_binding_count": text.count(
            _GENIUS_FOUR_LENS_SIX_COMPARISON_MARKER
        ),
        "device_figure_binding_counts": {
            marker: text.count(marker)
            for marker in _GENIUS_FOUR_LENS_SIX_DEVICE_MARKERS
        },
        "declared_figure_numbers": declared_figures,
        "html_table_count": len(re.findall(r"<table\b", raw_html, flags=re.IGNORECASE)),
        "html_system_label_counts": {
            "FNO": len(re.findall(r"\bFNO\b", text, flags=re.IGNORECASE)),
            "F-number": len(
                re.findall(r"\bF\s*[- ]?number\b", text, flags=re.IGNORECASE)
            ),
            "F/#": len(re.findall(r"\bF/#\b", text, flags=re.IGNORECASE)),
            "HFOV": len(re.findall(r"\bHFOV\b", text, flags=re.IGNORECASE)),
            "field of view": len(
                re.findall(r"\bfield of view\b", text, flags=re.IGNORECASE)
            ),
        },
    }


def _genius_four_lens_eleven_source_facts(raw_html: str) -> dict[str, Any]:
    """Bind all eleven optical/asphere figure pairs and their Fno comparison table."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker.split(" shows", maxsplit=1)[0]: text.count(marker)
            for marker in _GENIUS_FOUR_LENS_ELEVEN_REQUIRED_FIGURE_TEXT
        },
        "comparison_binding_counts": {
            marker: text.count(marker)
            for marker in _GENIUS_FOUR_LENS_ELEVEN_COMPARISON_MARKERS
        },
        "fno_label_count": len(re.findall(r"\bFno\b", text, flags=re.IGNORECASE)),
    }


def _genius_four_lens_eleven_source_layout(raw_html: str) -> dict[str, Any]:
    """Return an exact PDF layout pinned to one retained official HTML source."""

    digest = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()
    return genius_four_lens_eleven_source_layout_for_sha256(digest)


def genius_four_lens_eleven_source_layout_for_sha256(
    digest: str,
) -> dict[str, Any]:
    """Return the source-locked PDF layout for an official HTML digest."""

    layout = _GENIUS_FOUR_LENS_ELEVEN_SOURCE_LAYOUTS.get(digest)
    if layout is None:
        raise PatentPdfRecoveryError(
            "Genius four-lens eleven-embodiment official HTML is not source-locked"
        )
    return layout


def _genius_four_lens_nine_source_facts(raw_html: str) -> dict[str, Any]:
    """Bind all nine four-lens figure pairs and four comparison figures."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker.split(" shows", maxsplit=1)[0]: text.count(marker)
            for marker in _GENIUS_FOUR_LENS_NINE_REQUIRED_FIGURE_TEXT
        },
        "comparison_binding_counts": {
            marker.split(" show", maxsplit=1)[0]: text.count(marker)
            for marker in _GENIUS_FOUR_LENS_NINE_COMPARISON_MARKERS
        },
    }


def _genius_four_lens_eight_source_facts(raw_html: str) -> dict[str, Any]:
    """Bind the exact eight four-lens drawing-table denominator."""

    text = _normalized_html_text(raw_html)
    primary_digest = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()
    layout = _GENIUS_FOUR_LENS_EIGHT_SOURCE_LAYOUTS.get(primary_digest)
    if layout is None:
        raise PatentPdfRecoveryError(
            "Genius four-lens eight-embodiment official HTML is not source-locked"
        )
    normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if normalized_digest != layout["normalized_text_sha256"]:
        raise PatentPdfRecoveryError(
            "Genius four-lens eight-embodiment normalized HTML changed"
        )
    paragraph_numbers = tuple(int(value) for value in re.findall(r"\[(\d{4})\]", raw_html))
    claim_numbers = tuple(
        int(value)
        for value in re.findall(
            r"(?:^|\s)((?:[1-9]|1\d|20))\s+\.\s+(?:An|The) optical imaging lens",
            text,
        )
    )
    table_object_ids = tuple(dict.fromkeys(re.findall(r"TABLE-US-[0-9]+", raw_html)))
    math_object_ids = tuple(
        re.findall(r'<maths\b[^>]*\bid="([^"]+)"', raw_html, flags=re.IGNORECASE)
    )
    brief_drawings = raw_html[
        raw_html.index("BRIEF DESCRIPTION OF THE DRAWINGS") : raw_html.index(
            "DETAILED DESCRIPTION"
        )
    ]
    return {
        "primary_html_sha256": primary_digest,
        "normalized_text_sha256": normalized_digest,
        "application_number": layout["application_number"],
        "family_id": layout["family_id"],
        "paragraph_count": len(paragraph_numbers),
        "paragraph_numbers_continuous": paragraph_numbers == tuple(range(1, 143)),
        "claim_numbers": list(claim_numbers),
        "figure_reference_tag_count": raw_html.count('<figref idref="DRAWINGS">'),
        "brief_figure_declaration_count": brief_drawings.count(
            '<figref idref="DRAWINGS">'
        ),
        "declared_figure_panel_count": 63,
        "figure_binding_counts": {
            marker.split(" shows", maxsplit=1)[0]: text.count(marker)
            for marker in _GENIUS_FOUR_LENS_EIGHT_REQUIRED_FIGURE_TEXT
        },
        "comparison_binding_count": text.count(
            _GENIUS_FOUR_LENS_EIGHT_COMPARISON_MARKER
        ),
        "system_metadata_binding_counts": {
            str(index): text.count(marker)
            for index, marker in enumerate(_GENIUS_FOUR_LENS_EIGHT_SYSTEM_METADATA, start=1)
        },
        "table_object_ids": list(table_object_ids),
        "math_object_ids": list(math_object_ids),
        "genius_applicant_assignee_count": text.count(
            "Genius Electronic Optical (Xiamen) Co., Ltd."
        ),
        "primary_wavelength_marker_count": text.count(
            "primary wavelength of the embodiment of the invention is 555 nm"
        ),
        "a2_omission_marker_count": text.count(
            "a.sub.2 coefficients of each example are 0"
        ),
    }


def _genius_nine_lens_eleven_source_facts(raw_html: str) -> dict[str, Any]:
    """Bind eleven nine-lens optical/asphere pairs and two comparison sheets."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker.split(" depicts", maxsplit=1)[0]: text.count(marker)
            for marker in _GENIUS_NINE_LENS_ELEVEN_REQUIRED_FIGURE_TEXT
        },
        "comparison_binding_counts": {
            marker: text.count(marker)
            for marker in _GENIUS_NINE_LENS_ELEVEN_COMPARISON_MARKERS
        },
        "genius_applicant_assignee_count": text.count(
            "Genius Electronic Optical (Xiamen) Co., Ltd."
        ),
    }


def _genius_eight_lens_fourteen_source_facts(raw_html: str) -> dict[str, Any]:
    """Bind fourteen eight-lens optical/asphere pairs and two comparison sheets."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker: text.count(marker)
            for marker in _GENIUS_EIGHT_LENS_FOURTEEN_REQUIRED_FIGURE_TEXT
        },
        "comparison_binding_counts": {
            marker: text.count(marker)
            for marker in _GENIUS_EIGHT_LENS_FOURTEEN_COMPARISON_MARKERS
        },
        "genius_applicant_assignee_count": text.count(
            "Genius Electronic Optical (Xiamen) Co., Ltd."
        ),
    }


def _ability_three_five_lens_source_layout(raw_html: str) -> dict[str, Any]:
    digest = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()
    layout = _ABILITY_THREE_FIVE_LENS_SOURCE_LAYOUTS.get(digest)
    if layout is None:
        raise PatentPdfRecoveryError(
            "Ability three-five-lens official HTML is not source-locked"
        )
    return {**layout, "role_pages": dict(_ABILITY_THREE_FIVE_LENS_ROLE_PAGES)}


def _ability_three_five_lens_source_facts(raw_html: str) -> dict[str, Any]:
    """Bind three five-lens prescriptions and prove angular field is unpublished."""

    text = _normalized_html_text(raw_html)
    digest = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()
    layout = _ability_three_five_lens_source_layout(raw_html)
    normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if normalized_digest != layout["normalized_text_sha256"]:
        raise PatentPdfRecoveryError(
            "Ability three-five-lens normalized official HTML hash changed"
        )

    figure_binding_counts = {
        role: len(re.findall(pattern, text, flags=re.IGNORECASE))
        for role, pattern in _ABILITY_THREE_FIVE_LENS_BINDING_PATTERNS.items()
    }
    if figure_binding_counts != dict.fromkeys(
        _ABILITY_THREE_FIVE_LENS_BINDING_PATTERNS,
        2,
    ):
        raise PatentPdfRecoveryError(
            "Ability three-five-lens official figure-binding denominator changed"
        )

    angular_field_patterns = {
        "FOV": r"\bFOV\b",
        "HFOV": r"\bHFOV\b",
        "field of view": r"\bfield\s+of\s+view\b",
        "viewing angle": r"\bviewing\s+angle\b",
        "angle of view": r"\bangle\s+of\s+view\b",
        "image height": r"\bimage\s+height\b",
    }
    angular_field_label_counts = {
        label: len(re.findall(pattern, text, flags=re.IGNORECASE))
        for label, pattern in angular_field_patterns.items()
    }
    if any(angular_field_label_counts.values()):
        raise PatentPdfRecoveryError(
            "Ability three-five-lens official HTML may publish angular-field metadata"
        )

    shape_coordinate_definition_counts = {
        "h": len(
            re.findall(
                r"distance\s+between\s+the\s+inflection\s+point\s+IF\s+and\s+"
                r"the\s+optical\s+axis\s+OA\s+is\s+h",
                text,
                flags=re.IGNORECASE,
            )
        ),
        "H": len(
            re.findall(
                r"distance\s+between\s+an\s+outer\s+edge\s+of\s+the\s+image-side\s+"
                r"surface\s+S\s*10\s+of\s+the\s+fifth\s+lens\s+L\s*5\s+and\s+"
                r"the\s+optical\s+axis\s+OA\s+is\s+H",
                text,
                flags=re.IGNORECASE,
            )
        ),
    }
    if shape_coordinate_definition_counts != {"h": 1, "H": 1}:
        raise PatentPdfRecoveryError(
            "Ability three-five-lens h/H shape-coordinate definitions changed"
        )

    return {
        "primary_html_sha256": digest,
        "normalized_text_sha256": normalized_digest,
        "family_id": "74187659",
        "application_number": layout["application_number"],
        "prescription_count": 3,
        "lens_element_count": 5,
        "figure_binding_counts": figure_binding_counts,
        "angular_field_label_counts": angular_field_label_counts,
        "shape_coordinate_definition_counts": shape_coordinate_definition_counts,
    }


def ability_four_wide_angle_source_layout_for_sha256(
    digest: str,
) -> dict[str, Any]:
    """Return the source-locked four-prescription wide-angle layout."""

    layout = _ABILITY_FOUR_WIDE_ANGLE_SOURCE_LAYOUTS.get(digest)
    if layout is None:
        raise PatentPdfRecoveryError(
            "Ability four-wide-angle official HTML is not source-locked"
        )
    return {**layout, "role_pages": dict(_ABILITY_FOUR_WIDE_ANGLE_ROLE_PAGES)}


def _ability_four_wide_angle_source_layout(raw_html: str) -> dict[str, Any]:
    digest = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()
    return ability_four_wide_angle_source_layout_for_sha256(digest)


def _ability_four_wide_angle_source_facts(raw_html: str) -> dict[str, Any]:
    """Bind four complete prescriptions and their 160-degree system table."""

    text = _normalized_html_text(raw_html)
    digest = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()
    layout = _ability_four_wide_angle_source_layout(raw_html)
    normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if normalized_digest != layout["normalized_text_sha256"]:
        raise PatentPdfRecoveryError(
            "Ability four-wide-angle normalized official HTML hash changed"
        )

    figure_binding_counts = {
        role: len(re.findall(pattern, text, flags=re.IGNORECASE))
        for role, pattern in _ABILITY_FOUR_WIDE_ANGLE_BINDING_PATTERNS.items()
    }
    if figure_binding_counts != {
        "surface_ol1": 2,
        "asphere_ol1": 2,
        "surface_ol2": 2,
        "asphere_ol2": 2,
        "surface_ol3": 2,
        "surface_ol4": 2,
        "system_meta": 2,
    }:
        raise PatentPdfRecoveryError(
            "Ability four-wide-angle official figure-binding denominator changed"
        )

    paragraph_numbers = tuple(
        int(number) for number in re.findall(r"\[(\d{4})\]", text)
    )
    if paragraph_numbers != tuple(range(1, 67)):
        raise PatentPdfRecoveryError(
            "Ability four-wide-angle 66-paragraph denominator changed"
        )
    brief_description_panels = tuple(
        re.findall(
            r"\[(?:0009|001[0-9])\]\s+FIG\s*\.\s*(\d+[AB]?)",
            text,
            flags=re.IGNORECASE,
        )
    )
    if brief_description_panels != (
        "1",
        "2",
        "3A",
        "3B",
        "4A",
        "4B",
        "5",
        "6",
        "7",
        "8",
        "9",
    ):
        raise PatentPdfRecoveryError(
            "Ability four-wide-angle 11-panel drawing denominator changed"
        )
    claims_text = text[text.rfind("Claims ") :]
    claim_numbers = tuple(
        int(number)
        for number in re.findall(
            r"(?:^|\s)(\d{1,2})\s*\.\s+(?:An|The)\s+optical\s+lens",
            claims_text,
            flags=re.IGNORECASE,
        )
    )
    if claim_numbers != tuple(range(1, 21)):
        raise PatentPdfRecoveryError(
            "Ability four-wide-angle 20-claim denominator changed"
        )
    if raw_html.count('<maths id="MATH-US-00001"') != 1:
        raise PatentPdfRecoveryError(
            "Ability four-wide-angle MathML equation denominator changed"
        )

    return {
        "primary_html_sha256": digest,
        "normalized_text_sha256": normalized_digest,
        "family_id": layout["family_id"],
        "application_number": layout["application_number"],
        "figure_binding_counts": figure_binding_counts,
        "paragraph_ranges": {
            "background_summary": [1, 8],
            "description": [9, 66],
            "claims": [1, 20],
        },
        "brief_description_panels": list(brief_description_panels),
        "claim_numbers": list(claim_numbers),
        "independent_claim_numbers": [1, 8, 14],
        "formal_html_table_count": 0,
        "mathml_equation_count": 1,
        "sample_design_count": 4,
        "lens_element_counts": [10, 10, 11, 11],
    }


def genius_seven_lens_seven_source_layout_for_sha256(
    digest: str,
) -> dict[str, Any]:
    """Return the source-locked seven-example official PDF layout."""

    layout = _GENIUS_SEVEN_LENS_SEVEN_SOURCE_LAYOUTS.get(digest)
    if layout is None:
        raise PatentPdfRecoveryError(
            "Genius seven-lens seven-example official HTML is not source-locked"
        )
    return layout


def _genius_seven_lens_seven_source_layout(raw_html: str) -> dict[str, Any]:
    digest = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()
    layout = genius_seven_lens_seven_source_layout_for_sha256(digest)
    normalized_digest = hashlib.sha256(
        _normalized_html_text(raw_html).encode("utf-8")
    ).hexdigest()
    if normalized_digest != layout["normalized_text_sha256"]:
        raise PatentPdfRecoveryError(
            "Genius seven-lens seven-example normalized official HTML hash changed"
        )
    return layout


def _genius_seven_lens_seven_source_facts(raw_html: str) -> dict[str, Any]:
    """Bind seven image-table pairs, their comparison sheets, and prose metadata."""

    text = _normalized_html_text(raw_html)
    digest = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()
    layout = _genius_seven_lens_seven_source_layout(raw_html)
    number = r"(?:\d+(?:\.\d*)?|\.\d+)"
    system_pattern = re.compile(
        rf"TTL is (?P<ttl>{number}) mm\. Fno is (?P<fno>{number})\. "
        rf"The image height is (?P<image_height>{number}) mm\. "
        rf"HFOV is (?P<hfov>{number}) degrees\.",
        flags=re.IGNORECASE,
    )
    system_values = [
        {
            "ttl_mm": float(match.group("ttl")),
            "f_number": float(match.group("fno")),
            "image_height_mm": float(match.group("image_height")),
            "hfov_deg": float(match.group("hfov")),
        }
        for match in system_pattern.finditer(text)
    ]
    example_heading_counts = {
        ordinal: len(
            re.findall(
                rf"\b{ordinal}\s+example\s+(?:\[\d+\]|\(\d+\))\s+"
                rf"Please refer to FIG\. {6 + 2 * index}\b",
                text,
                flags=re.IGNORECASE,
            )
        )
        for index, ordinal in enumerate(_GENIUS_SEVEN_LENS_SEVEN_ORDINALS)
    }
    return {
        "primary_html_sha256": digest,
        "normalized_text_sha256": layout["normalized_text_sha256"],
        "family_id": layout["family_id"],
        "application_number": layout["application_number"],
        "figure_binding_counts": {
            marker: text.count(marker)
            for marker in _GENIUS_SEVEN_LENS_SEVEN_REQUIRED_FIGURE_TEXT
        },
        "comparison_binding_counts": {
            marker: text.count(marker)
            for marker in _GENIUS_SEVEN_LENS_SEVEN_COMPARISON_MARKERS
        },
        "example_heading_counts": example_heading_counts,
        "system_values": system_values,
        "genius_applicant_assignee_count": text.count(
            "Genius Electronic Optical (Xiamen) Co., Ltd."
        ),
    }


def _genius_six_lens_five_source_facts(raw_html: str) -> dict[str, Any]:
    """Bind all five optical/asphere pairs and their two comparison sheets."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker.split(" shows", maxsplit=1)[0]: text.count(marker)
            for marker in _GENIUS_SIX_LENS_FIVE_REQUIRED_FIGURE_TEXT
        },
        "comparison_binding_count": text.count(_GENIUS_SIX_LENS_FIVE_COMPARISON_MARKER),
    }


def _genius_six_lens_nine_source_facts(raw_html: str) -> dict[str, Any]:
    """Bind all nine optical/asphere pairs and their two comparison sheets."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker.split(" shows", maxsplit=1)[0]: text.count(marker)
            for marker in _GENIUS_SIX_LENS_NINE_REQUIRED_FIGURE_TEXT
        },
        "comparison_binding_counts": {
            marker.split(" shows", maxsplit=1)[0]: text.count(marker)
            for marker in _GENIUS_SIX_LENS_NINE_COMPARISON_MARKERS
        },
    }


def _genius_six_lens_ten_dual_focus_source_facts(raw_html: str) -> dict[str, Any]:
    """Bind ten dual-focus optical/asphere pairs and four comparison sheets."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker: text.count(marker)
            for marker in _GENIUS_SIX_LENS_TEN_DUAL_FOCUS_REQUIRED_FIGURE_TEXT
        },
        "comparison_binding_count": text.count(
            _GENIUS_SIX_LENS_TEN_DUAL_FOCUS_COMPARISON_MARKER
        ),
        "first_focusing_state_count": text.count("first focusing state"),
        "second_focusing_state_count": text.count("second focusing state"),
        "six_lens_element_claim_count": text.count(
            "optical imaging lens of six lens elements"
        ),
    }


def _genius_six_lens_nine_three_comparison_source_facts(
    raw_html: str,
) -> dict[str, Any]:
    """Bind the nine figure pairs and three comparison sheets."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker.split(" shows", maxsplit=1)[0]: text.count(marker)
            for marker in _GENIUS_SIX_LENS_NINE_THREE_COMPARISON_REQUIRED_FIGURE_TEXT
        },
        "comparison_binding_counts": {
            marker.split(" shows", maxsplit=1)[0]: text.count(marker)
            for marker in _GENIUS_SIX_LENS_NINE_THREE_COMPARISON_MARKERS
        },
    }


def _genius_six_lens_nine_four_comparison_source_facts(
    raw_html: str,
) -> dict[str, Any]:
    """Bind the nine figure pairs and the four-sheet comparison references."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker.split(" illustrates", maxsplit=1)[0]: text.count(marker)
            for marker in _GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_REQUIRED_FIGURE_TEXT
        },
        "comparison_binding_counts": {
            marker: text.count(marker)
            for marker in _GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_MARKERS
        },
    }


async def _google_citation_pdf_urls(
    client: httpx.AsyncClient,
    google_page_url: str,
    *,
    profile: str,
) -> set[str]:
    """Return citation PDFs, allowing proven official-only profiles on Google 404."""

    try:
        google_page = await _get_with_retries(
            client,
            google_page_url,
            headers={"Accept": "text/html"},
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404 and profile in _GENIUS_OFFICIAL_ONLY_PROFILES:
            return set()
        raise
    return {
        html.unescape(match.group("url"))
        for match in _GOOGLE_PDF_META_RE.finditer(google_page.text)
    }


def _compact_publication_id(publication_id: str) -> tuple[str, str]:
    match = re.fullmatch(r"US-(?P<number>\d+)-(?P<kind>[A-Z]\d+)", publication_id.upper())
    if match is None:
        raise PatentPdfRecoveryError(f"unsupported USPTO publication id: {publication_id}")
    compact = f"US{match.group('number')}{match.group('kind')}"
    return compact, match.group("number")


async def _get_with_retries(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    response: httpx.Response | None = None
    for attempt in range(4):
        response = await client.get(
            url,
            params=params,
            headers=headers,
            follow_redirects=True,
        )
        if response.status_code != 429:
            response.raise_for_status()
            return response
        await asyncio.sleep(5 * (attempt + 1))
    assert response is not None
    response.raise_for_status()
    return response


def _require_pdf(content: bytes, *, source: str) -> None:
    if not content.startswith(_PDF_HEADER):
        raise PatentPdfRecoveryError(f"{source} did not return a PDF")


def _page_image(page: pypdf._page.PageObject, *, source: str, page_number: int) -> bytes:
    images = list(page.images)
    if len(images) != 1:
        raise PatentPdfRecoveryError(
            f"{source} page {page_number} contains {len(images)} images; expected exactly one"
        )
    return images[0].data


def _decoded_raster(image_bytes: bytes, *, source: str) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise PatentPdfRecoveryError(f"{source} page image could not be decoded")
    return np.ascontiguousarray(image)


def _canonical_raster_sha256(image_bytes: bytes) -> str:
    """Hash decoded pixels, excluding nondeterministic TIFF container padding."""

    image = _decoded_raster(image_bytes, source="canonical")
    digest = hashlib.sha256()
    digest.update(b"decoded-page-raster-v1\0")
    digest.update(str(image.shape).encode("ascii"))
    digest.update(b"\0")
    digest.update(str(image.dtype).encode("ascii"))
    digest.update(b"\0")
    digest.update(image.tobytes(order="C"))
    return digest.hexdigest()


def _figure_page(texts: list[str], figure: str, required: tuple[str, ...]) -> int:
    figure_pattern = re.compile(rf"\bFIG\s*\.\s*{re.escape(figure)}\b", re.IGNORECASE)
    drawing_sheet_pattern = re.compile(r"\bSheet\s+\d+\s+of\s+\d+\b", re.IGNORECASE)
    matches = [
        index
        for index, text in enumerate(texts)
        if drawing_sheet_pattern.search(text)
        and figure_pattern.search(text)
        and all(item.lower() in text.lower() for item in required)
    ]
    if len(matches) != 1:
        raise PatentPdfRecoveryError(
            f"Ability PDF figure {figure} key page count is {len(matches)}; expected one"
        )
    return matches[0]


def _rapidocr_tokens(
    image_bytes: bytes,
    *,
    rotation: str | None = None,
    scale: float | None = None,
) -> list[dict[str, Any]]:
    image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise PatentPdfRecoveryError("official page image could not be decoded")
    if rotation == "clockwise_90":
        image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    elif rotation == "counterclockwise_90":
        image = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    elif rotation is not None:
        raise PatentPdfRecoveryError(f"unsupported RapidOCR rotation: {rotation}")
    if scale is not None:
        if not 0.0 < scale <= 1.0:
            raise PatentPdfRecoveryError("RapidOCR scale must be in (0, 1]")
        image = cv2.resize(
            image,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_AREA,
        )
    engine = RapidOCR()
    result, _elapsed = engine(image)
    tokens: list[dict[str, Any]] = []
    for box, text, confidence in result or []:
        tokens.append(
            {
                "box": [[round(float(x), 3), round(float(y), 3)] for x, y in box],
                "text": str(text),
                "confidence": round(float(confidence), 6),
            }
        )
    return tokens


def _canonical_parser_input(
    *,
    publication_id: str,
    page_count: int,
    key_pages: list[tuple[int, str, str, str, list[dict[str, Any]]]],
    profile: str | None = None,
    source_facts: dict[str, Any] | None = None,
    rapidocr_rotation: str | None = None,
    page_ocr_metadata: dict[str, dict[str, Any]] | None = None,
) -> bytes:
    pages: list[dict[str, Any]] = []
    for page_number, role, image_sha256, mirror_text, tokens in key_pages:
        page = {
            "page_number": page_number,
            "role": role,
            "official_image_sha256": image_sha256,
            "mirror_text": mirror_text,
            "rapidocr_tokens": tokens,
        }
        if rapidocr_rotation is not None:
            page["rapidocr_rotation"] = rapidocr_rotation
        if page_ocr_metadata is not None:
            page.update(page_ocr_metadata.get(role, {}))
        pages.append(page)
    payload = {
        "schema_version": 1,
        "parser_family": "ability_official_pdf_ocr_v1",
        "publication_id": publication_id,
        "page_count": page_count,
        "pages": pages,
    }
    # Keep the first profile's canonical bytes stable.  New profile metadata is
    # emitted only for layouts which need additional source-level proof.
    if profile is not None:
        payload["profile"] = profile
    if source_facts is not None:
        payload["source_facts"] = source_facts
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


async def recover_ability_official_pdf_ocr(
    client: httpx.AsyncClient,
    token: str,
    *,
    publication_id: str,
    primary_html: str,
    cached_sources: PatentPdfCachedSources | None = None,
) -> PatentPdfOcrRecovery | None:
    """Recover a strict Ability image-table layout or return no match."""

    profile = _ability_layout_profile(primary_html)
    if profile is None:
        return None
    compact_id, patent_number = _compact_publication_id(publication_id)
    official_url = USPTO_IMAGE_PDF_URL.format(patent_number=patent_number)
    if cached_sources is None:
        official_response = await _get_with_retries(
            client,
            official_url,
            params={"requestToken": token},
            headers={
                "Accept": "application/pdf",
                "Referer": "https://ppubs.uspto.gov/",
                "x-access-token": token,
            },
        )
        official_pdf = official_response.content
    else:
        if cached_sources.official_pdf_url != official_url:
            raise PatentPdfRecoveryError("cached USPTO PDF URL does not match publication")
        official_pdf = cached_sources.official_pdf
    _require_pdf(official_pdf, source="USPTO image PDF")

    if cached_sources is None:
        google_page_url = GOOGLE_PATENT_URL.format(compact_publication_id=compact_id)
        pdf_urls = await _google_citation_pdf_urls(
            client,
            google_page_url,
            profile=profile,
        )
        if not pdf_urls and profile in _GENIUS_OFFICIAL_ONLY_PROFILES:
            mirror_url = None
        elif len(pdf_urls) != 1:
            raise PatentPdfRecoveryError(
                f"Google patent citation PDF count is {len(pdf_urls)}; expected one"
            )
        else:
            mirror_url = next(iter(pdf_urls))
    else:
        mirror_url = cached_sources.mirror_pdf_url
    if mirror_url is not None:
        parsed_url = httpx.URL(mirror_url)
        if parsed_url.scheme != "https" or parsed_url.host != GOOGLE_PDF_HOST:
            raise PatentPdfRecoveryError("Google citation PDF URL is outside the allowed host")
    if cached_sources is None and mirror_url is not None:
        mirror_response = await _get_with_retries(
            client,
            mirror_url,
            headers={"Accept": "application/pdf"},
        )
        mirror_pdf = mirror_response.content
    elif cached_sources is not None:
        mirror_pdf = cached_sources.mirror_pdf
    else:
        mirror_pdf = None
    if mirror_pdf is not None:
        _require_pdf(mirror_pdf, source="Google patent OCR PDF")
    if (mirror_pdf is None) != (mirror_url is None):
        raise PatentPdfRecoveryError("Google OCR PDF URL/content availability differs")

    snap_six_lens_layout: dict[str, Any] | None = None
    if profile == _SNAP_SIX_LENS_TWO_DESIGN_PROFILE:
        snap_six_lens_layout = _snap_six_lens_two_design_source_layout(
            primary_html
        )
        if mirror_pdf is None:
            raise PatentPdfRecoveryError(
                "Snap six-lens two-design mirror PDF is unavailable"
            )
    genius_four_lens_six_layout: dict[str, Any] | None = None
    if profile == _GENIUS_FOUR_LENS_SIX_PROFILE:
        genius_four_lens_six_layout = _genius_four_lens_six_source_layout(primary_html)
        if mirror_pdf is None:
            raise PatentPdfRecoveryError(
                "Genius four-lens six-embodiment mirror PDF is unavailable"
            )
    genius_four_lens_layout: dict[str, Any] | None = None
    if profile == _GENIUS_FOUR_LENS_ELEVEN_PROFILE:
        genius_four_lens_layout = _genius_four_lens_eleven_source_layout(primary_html)
        if mirror_pdf is None:
            raise PatentPdfRecoveryError("Genius mirror PDF is unavailable")
    circle_optics_layout: dict[str, Any] | None = None
    if profile == _CIRCLE_OPTICS_SEVEN_LENS_PROFILE:
        circle_optics_layout = _circle_optics_seven_lens_source_layout(primary_html)
    kodak_low_stress_layout: dict[str, Any] | None = None
    if profile == _KODAK_LOW_STRESS_TWO_LENS_PROFILE:
        kodak_low_stress_layout = _kodak_low_stress_source_layout(primary_html)
        if mirror_pdf is None:
            raise PatentPdfRecoveryError("Kodak low-stress mirror PDF is unavailable")
    ability_five_three_layout: dict[str, Any] | None = None
    if profile == _ABILITY_FIVE_THREE_LENS_PROFILE:
        ability_five_three_layout = _ability_five_three_lens_source_layout(primary_html)
        if mirror_pdf is None:
            raise PatentPdfRecoveryError("Ability five-three-lens mirror PDF is unavailable")
    ability_three_five_layout: dict[str, Any] | None = None
    if profile == _ABILITY_THREE_FIVE_LENS_PROFILE:
        ability_three_five_layout = _ability_three_five_lens_source_layout(primary_html)
        if mirror_pdf is None:
            raise PatentPdfRecoveryError("Ability three-five-lens mirror PDF is unavailable")
    ability_four_wide_layout: dict[str, Any] | None = None
    if profile == _ABILITY_FOUR_WIDE_ANGLE_PROFILE:
        ability_four_wide_layout = _ability_four_wide_angle_source_layout(primary_html)
        if mirror_pdf is None:
            raise PatentPdfRecoveryError("Ability four-wide-angle mirror PDF is unavailable")
    aac_two_three_layout: dict[str, Any] | None = None
    if profile == _AAC_TWO_THREE_LENS_PROFILE:
        aac_two_three_layout = _aac_two_three_lens_source_layout(primary_html)
        if mirror_pdf is None:
            raise PatentPdfRecoveryError("AAC two-three-lens mirror PDF is unavailable")

    official_reader = pypdf.PdfReader(io.BytesIO(official_pdf))
    mirror_reader = pypdf.PdfReader(io.BytesIO(mirror_pdf)) if mirror_pdf is not None else None
    if mirror_reader is not None and len(official_reader.pages) != len(mirror_reader.pages):
        raise PatentPdfRecoveryError("official and OCR PDFs have different page counts")
    page_count = len(official_reader.pages)
    mirror_texts = (
        [page.extract_text() or "" for page in mirror_reader.pages]
        if mirror_reader is not None
        else [""] * page_count
    )
    blank_mirror_pages = {
        page_number
        for page_number, text in enumerate(mirror_texts, start=1)
        if not text.strip()
    }
    if profile == _SNAP_SIX_LENS_TWO_DESIGN_PROFILE:
        assert snap_six_lens_layout is not None
        expected_blank_pages = snap_six_lens_layout["blank_mirror_pages"]
        if blank_mirror_pages != expected_blank_pages:
            raise PatentPdfRecoveryError(
                "Snap six-lens two-design OCR overlay blank-page set changed: actual="
                + ",".join(str(page) for page in sorted(blank_mirror_pages))
                + " expected="
                + ",".join(str(page) for page in sorted(expected_blank_pages))
            )
    elif profile == _GENIUS_FOUR_LENS_SIX_PROFILE:
        assert genius_four_lens_six_layout is not None
        expected_blank_pages = genius_four_lens_six_layout["blank_mirror_pages"]
        if blank_mirror_pages != expected_blank_pages:
            raise PatentPdfRecoveryError(
                "Genius four-lens six-embodiment OCR overlay blank-page set changed: actual="
                + ",".join(str(page) for page in sorted(blank_mirror_pages))
                + " expected="
                + ",".join(str(page) for page in sorted(expected_blank_pages))
            )
    elif profile == _GENIUS_FOUR_LENS_ELEVEN_PROFILE:
        assert genius_four_lens_layout is not None
        expected_blank_pages = genius_four_lens_layout["blank_mirror_pages"]
        if blank_mirror_pages != expected_blank_pages:
            raise PatentPdfRecoveryError(
                "Genius OCR overlay blank-page set changed: actual="
                + ",".join(str(page) for page in sorted(blank_mirror_pages))
                + " expected="
                + ",".join(str(page) for page in sorted(expected_blank_pages))
            )
    elif profile == _KODAK_LOW_STRESS_TWO_LENS_PROFILE:
        assert kodak_low_stress_layout is not None
        expected_blank_pages = kodak_low_stress_layout["blank_mirror_pages"]
        if blank_mirror_pages != expected_blank_pages:
            raise PatentPdfRecoveryError(
                "Kodak low-stress OCR overlay blank-page set changed: actual="
                + ",".join(str(page) for page in sorted(blank_mirror_pages))
                + " expected="
                + ",".join(str(page) for page in sorted(expected_blank_pages))
            )
    elif profile == _ABILITY_FIVE_THREE_LENS_PROFILE:
        assert ability_five_three_layout is not None
        expected_blank_pages = ability_five_three_layout["blank_mirror_pages"]
        if blank_mirror_pages != expected_blank_pages:
            raise PatentPdfRecoveryError(
                "Ability five-three-lens OCR overlay blank-page set changed: actual="
                + ",".join(str(page) for page in sorted(blank_mirror_pages))
                + " expected="
                + ",".join(str(page) for page in sorted(expected_blank_pages))
            )
    elif profile == _ABILITY_THREE_FIVE_LENS_PROFILE:
        assert ability_three_five_layout is not None
        expected_blank_pages = ability_three_five_layout["blank_mirror_pages"]
        if blank_mirror_pages != expected_blank_pages:
            raise PatentPdfRecoveryError(
                "Ability three-five-lens OCR overlay blank-page set changed: actual="
                + ",".join(str(page) for page in sorted(blank_mirror_pages))
                + " expected="
                + ",".join(str(page) for page in sorted(expected_blank_pages))
            )
    elif profile == _ABILITY_FOUR_WIDE_ANGLE_PROFILE:
        assert ability_four_wide_layout is not None
        expected_blank_pages = ability_four_wide_layout["blank_mirror_pages"]
        if blank_mirror_pages != expected_blank_pages:
            raise PatentPdfRecoveryError(
                "Ability four-wide-angle OCR overlay blank-page set changed: actual="
                + ",".join(str(page) for page in sorted(blank_mirror_pages))
                + " expected="
                + ",".join(str(page) for page in sorted(expected_blank_pages))
            )
    elif profile == _AAC_TWO_THREE_LENS_PROFILE:
        assert aac_two_three_layout is not None
        expected_blank_pages = aac_two_three_layout["blank_mirror_pages"]
        if blank_mirror_pages != expected_blank_pages:
            raise PatentPdfRecoveryError(
                "AAC two-three-lens OCR overlay blank-page set changed: actual="
                + ",".join(str(page) for page in sorted(blank_mirror_pages))
                + " expected="
                + ",".join(str(page) for page in sorted(expected_blank_pages))
            )
    elif profile in _GENIUS_OFFICIAL_ONLY_PROFILES:
        # This exact profile does not use mirror text. When an overlay is
        # published, every decoded raster is checked above; otherwise only the
        # official USPTO rasters are retained. Key pages always use RapidOCR.
        pass
    elif blank_mirror_pages:
        raise PatentPdfRecoveryError(
            "Google citation PDF lacks an OCR text layer on one or more pages"
        )

    page_hashes: list[str] = []
    official_images: list[bytes] = []
    for page_number, official_page in enumerate(official_reader.pages, start=1):
        official_image = _page_image(
            official_page,
            source="USPTO",
            page_number=page_number,
        )
        if mirror_reader is not None:
            mirror_image = _page_image(
                mirror_reader.pages[page_number - 1],
                source="Google OCR",
                page_number=page_number,
            )
            official_raster = _decoded_raster(
                official_image,
                source=f"USPTO page {page_number}",
            )
            mirror_raster = _decoded_raster(
                mirror_image,
                source=f"Google OCR page {page_number}",
            )
            if (
                official_raster.shape != mirror_raster.shape
                or official_raster.dtype != mirror_raster.dtype
                or not np.array_equal(official_raster, mirror_raster)
            ):
                raise PatentPdfRecoveryError(
                    f"official/OCR decoded page raster mismatch at page {page_number}"
                )
        page_hashes.append(_canonical_raster_sha256(official_image))
        official_images.append(official_image)

    if profile == _SNAP_SIX_LENS_TWO_DESIGN_PROFILE:
        assert snap_six_lens_layout is not None
        if tuple(page_hashes) != snap_six_lens_layout["page_image_sha256"]:
            raise PatentPdfRecoveryError(
                "Snap six-lens two-design full PDF raster denominator changed"
            )
    if profile == _ABILITY_THREE_FIVE_LENS_PROFILE:
        assert ability_three_five_layout is not None
        expected_page_hashes = ability_three_five_layout["page_image_sha256"]
        if tuple(page_hashes) != expected_page_hashes:
            raise PatentPdfRecoveryError(
                "Ability three-five-lens full PDF raster denominator changed"
            )
    if profile == _ABILITY_FOUR_WIDE_ANGLE_PROFILE:
        assert ability_four_wide_layout is not None
        expected_page_hashes = ability_four_wide_layout["page_image_sha256"]
        if tuple(page_hashes) != expected_page_hashes:
            raise PatentPdfRecoveryError(
                "Ability four-wide-angle full PDF raster denominator changed"
            )
    if profile == _GENIUS_FOUR_LENS_SIX_PROFILE:
        assert genius_four_lens_six_layout is not None
        expected_page_hashes = genius_four_lens_six_layout["page_image_sha256"]
        if tuple(page_hashes) != expected_page_hashes:
            raise PatentPdfRecoveryError(
                "Genius four-lens six-embodiment full PDF raster denominator changed"
            )

    rapidocr_rotation: str | None = None
    page_ocr_metadata: dict[str, dict[str, Any]] = {}
    if profile == _SNAP_SIX_LENS_TWO_DESIGN_PROFILE:
        assert snap_six_lens_layout is not None
        if page_count != snap_six_lens_layout["page_count"]:
            raise PatentPdfRecoveryError(
                "Snap six-lens two-design PDF page count changed: "
                f"actual={page_count} expected={snap_six_lens_layout['page_count']}"
            )
        role_pages = dict(snap_six_lens_layout["role_pages"])
        for role, page_index in role_pages.items():
            sheet_number = page_index - 1
            normalized_mirror = re.sub(r"\s+", " ", mirror_texts[page_index])
            if re.search(
                rf"\bSheet\s+{sheet_number}\s+of\s*8\b",
                normalized_mirror,
                flags=re.IGNORECASE,
            ) is None:
                raise PatentPdfRecoveryError(
                    f"Snap six-lens role {role} lacks its drawing-sheet header"
                )
        parser_profile = profile
        source_facts = _snap_six_lens_two_design_source_facts(primary_html)
        rapidocr_rotation = "clockwise_90"
    elif profile == _GENIUS_FOUR_LENS_SIX_PROFILE:
        assert genius_four_lens_six_layout is not None
        if page_count != genius_four_lens_six_layout["page_count"]:
            raise PatentPdfRecoveryError(
                "Genius four-lens six-embodiment PDF page count changed: "
                f"actual={page_count} expected={genius_four_lens_six_layout['page_count']}"
            )
        role_pages = dict(genius_four_lens_six_layout["role_pages"])
        parser_profile = profile
        source_facts = _genius_four_lens_six_source_facts(primary_html)
    elif profile == _CIRCLE_OPTICS_SEVEN_LENS_PROFILE:
        assert circle_optics_layout is not None
        if page_count != circle_optics_layout["page_count"]:
            raise PatentPdfRecoveryError(
                "Circle Optics seven-lens PDF page count changed: "
                f"actual={page_count} expected={circle_optics_layout['page_count']}"
            )
        role_pages = dict(circle_optics_layout["role_pages"])
        parser_profile = profile
        source_facts = _circle_optics_seven_lens_source_facts(primary_html)
        rapidocr_rotation = "clockwise_90"
    elif profile == _KODAK_LOW_STRESS_TWO_LENS_PROFILE:
        assert kodak_low_stress_layout is not None
        if page_count != kodak_low_stress_layout["page_count"]:
            raise PatentPdfRecoveryError(
                "Kodak low-stress PDF page count changed: "
                f"actual={page_count} expected={kodak_low_stress_layout['page_count']}"
            )
        role_pages = dict(kodak_low_stress_layout["role_pages"])
        parser_profile = profile
        source_facts = _kodak_low_stress_source_facts(primary_html)
        rapidocr_rotation = "counterclockwise_90"
    elif profile == _ABILITY_THREE_FIVE_LENS_PROFILE:
        assert ability_three_five_layout is not None
        if page_count != ability_three_five_layout["page_count"]:
            raise PatentPdfRecoveryError(
                "Ability three-five-lens PDF page count changed: "
                f"actual={page_count} expected={ability_three_five_layout['page_count']}"
            )
        role_pages = dict(ability_three_five_layout["role_pages"])
        parser_profile = profile
        source_facts = _ability_three_five_lens_source_facts(primary_html)
    elif profile == _ABILITY_FOUR_WIDE_ANGLE_PROFILE:
        assert ability_four_wide_layout is not None
        if page_count != ability_four_wide_layout["page_count"]:
            raise PatentPdfRecoveryError(
                "Ability four-wide-angle PDF page count changed: "
                f"actual={page_count} expected={ability_four_wide_layout['page_count']}"
            )
        role_pages = dict(ability_four_wide_layout["role_pages"])
        parser_profile = profile
        source_facts = _ability_four_wide_angle_source_facts(primary_html)
    elif profile == "ability_two_lens_prescriptions_v1":
        role_pages = {
            "surface_ol1": _figure_page(
                mirror_texts,
                "2A",
                ("Lens", "Surface", "Curvature", "Thickness", "Abbe"),
            ),
            "asphere_ol1": _figure_page(
                mirror_texts,
                "2B",
                ("S7", "S8", "A6", "A16"),
            ),
            "surface_ol2": _figure_page(
                mirror_texts,
                "5",
                ("Lens", "Surface", "Curvature", "Thickness", "Abbe"),
            ),
            "system_meta": _figure_page(
                mirror_texts,
                "7",
                ("OL1", "OL2", "FOV", "FNO"),
            ),
        }
        parser_profile = None
        source_facts = None
    elif profile == _ABILITY_EIGHT_LENS_PROFILE:
        role_pages = {
            "surface_single": _figure_page(
                mirror_texts,
                "2",
                ("Surface", "Curvature", "Thickness", "Abbe", "Conic"),
            ),
            "asphere_single": _figure_page(
                mirror_texts,
                "3",
                ("Aspheric", "coefficient", "A4", "A16"),
            ),
        }
        parser_profile = profile
        source_facts = _ability_eight_lens_source_facts(primary_html)
    elif profile == _ABILITY_THREE_LENS_PROFILE:
        role_pages = {
            "prescription_ol1": _figure_page(
                mirror_texts,
                "4A",
                ("surface", "curvature", "thickness", "abbe", "A16"),
            ),
            "prescription_ol2": _figure_page(
                mirror_texts,
                "5A",
                ("surface", "curvature", "thickness", "abbe", "A16"),
            ),
            "prescription_ol3": _figure_page(
                mirror_texts,
                "6A",
                ("surface", "curvature", "thickness", "abbe", "A16"),
            ),
            "system_meta_three": _figure_page(
                mirror_texts,
                "7",
                ("optical lens", "OL1", "OL3", "FNO", "FOV"),
            ),
        }
        parser_profile = profile
        source_facts = _ability_three_lens_source_facts(primary_html)
    elif profile == _ABILITY_TWO_FIVE_LENS_PROFILE:
        role_pages = {
            "prescription_five_ol1": _figure_page(
                mirror_texts,
                "3A",
                ("Surface", "Radius", "Thickness", "Abbe", "A12", "K"),
            ),
            "prescription_five_ol2": _figure_page(
                mirror_texts,
                "4A",
                ("Surface", "Radius", "Thickness", "Abbe", "A12", "K"),
            ),
            "system_meta_five": _figure_page(
                mirror_texts,
                "5",
                ("OL1", "OL2", "Fno", "FOV"),
            ),
        }
        parser_profile = profile
        source_facts = _ability_two_five_lens_source_facts(primary_html)
    elif profile == _ABILITY_TWO_NINE_LENS_PROFILE:
        role_pages = {
            "prescription_nine_ol1": _figure_page(
                mirror_texts,
                "4A",
                ("Surface", "Curvature", "Thickness", "Abbe", "K", "A12"),
            ),
            "prescription_nine_ol2": _figure_page(
                mirror_texts,
                "5A",
                ("Surface", "Curvature", "Thickness", "Abbe", "K", "A12"),
            ),
            "system_meta_nine": _figure_page(
                mirror_texts,
                "6",
                ("Optical lens OL1", "Optical lens OL2", "TTL", "FOV"),
            ),
        }
        parser_profile = profile
        source_facts = _ability_two_nine_lens_source_facts(primary_html)
    elif profile == _ABILITY_FOUR_EIGHT_LENS_PROFILE:
        role_pages = {
            "prescription_eight_ol1": _figure_page(
                mirror_texts,
                "2A",
                ("Surface", "Curvature", "Thickness", "Abbe", "A12"),
            ),
            "prescription_eight_ol2": _figure_page(
                mirror_texts,
                "4A",
                ("Surface", "Curvature", "Thickness", "Abbe", "A12"),
            ),
            "prescription_eight_ol3": _figure_page(
                mirror_texts,
                "6A",
                ("Surface", "Curvature", "Thickness", "Abbe", "A12"),
            ),
            "prescription_eight_ol4": _figure_page(
                mirror_texts,
                "8",
                ("Surface", "Curvature", "Thickness", "Abbe"),
            ),
            "system_meta_four_eight": _figure_page(
                mirror_texts,
                "9",
                ("Optical lens OL1", "Optical lens OL4", "F1", "R1"),
            ),
        }
        parser_profile = profile
        source_facts = _ability_four_eight_lens_source_facts(primary_html)
    elif profile == _ABILITY_FIVE_THREE_LENS_PROFILE:
        assert ability_five_three_layout is not None
        if page_count != ability_five_three_layout["page_count"]:
            raise PatentPdfRecoveryError(
                "Ability five-three-lens PDF page count changed: "
                f"actual={page_count} expected={ability_five_three_layout['page_count']}"
            )
        role_pages = dict(ability_five_three_layout["role_pages"])
        for role, page_index in role_pages.items():
            mirror_text = mirror_texts[page_index]
            if mirror_text:
                sheet_number = page_index
                normalized_mirror = re.sub(r"\s+", " ", mirror_text)
                if re.search(
                    rf"\bSheet\s+{sheet_number}\s+of\s*21\b",
                    normalized_mirror,
                    flags=re.IGNORECASE,
                ) is None:
                    raise PatentPdfRecoveryError(
                        f"Ability five-three-lens role {role} lacks its drawing-sheet header"
                    )
        parser_profile = profile
        source_facts = _ability_five_three_lens_source_facts(primary_html)
    elif profile == _AAC_TWO_THREE_LENS_PROFILE:
        assert aac_two_three_layout is not None
        if page_count != aac_two_three_layout["page_count"]:
            raise PatentPdfRecoveryError(
                "AAC two-three-lens PDF page count changed: "
                f"actual={page_count} expected={aac_two_three_layout['page_count']}"
            )
        role_pages = dict(aac_two_three_layout["role_pages"])
        for sheet_number, page_index in enumerate(role_pages.values(), start=1):
            normalized_mirror = re.sub(r"\s+", " ", mirror_texts[page_index])
            if re.search(
                rf"\bSheet\s+{sheet_number}\s+of\s*2\b",
                normalized_mirror,
                flags=re.IGNORECASE,
            ) is None:
                raise PatentPdfRecoveryError(
                    f"AAC two-three-lens drawing sheet {sheet_number} header changed"
                )
        parser_profile = profile
        source_facts = _aac_two_three_lens_source_facts(primary_html)
    elif profile == _LARGAN_THREE_FIVE_LENS_PROFILE:
        role_pages = {
            "largan_surface_1": _figure_page(
                mirror_texts,
                "7",
                ("TABLE 1", "Embodiment 1", "Surface #", "Fno", "HFOV"),
            ),
            "largan_asphere_1": _figure_page(
                mirror_texts,
                "8",
                ("TABLE 2", "Aspheric Coefficients", "Surface #", "A16"),
            ),
            "largan_surface_2": _figure_page(
                mirror_texts,
                "9",
                ("TABLE 3", "Embodiment 2", "Surface #", "Fno", "HFOV"),
            ),
            "largan_asphere_2": _figure_page(
                mirror_texts,
                "10",
                ("TABLE4", "Aspheric Coefficients", "Surface #", "A14"),
            ),
            "largan_surface_3": _figure_page(
                mirror_texts,
                "11",
                ("TABLE 5", "Embodiment 3", "Surface #", "Fno", "HFOV"),
            ),
            "largan_asphere_3": _figure_page(
                mirror_texts,
                "12",
                ("TABLE 6", "Aspheric Coefficients", "Surface #", "A14"),
            ),
            "largan_system_meta": _figure_page(
                mirror_texts,
                "13",
                ("TABLE 7", "Embodiment", "Fno", "HFOV", "TTL", "ImgH"),
            ),
        }
        parser_profile = profile
        source_facts = _largan_three_five_lens_source_facts(primary_html)
    elif profile == _ABILITY_ZOOM_TWO_STATE_PROFILE:
        role_pages = {
            "ability_zoom_telescopic": _figure_page(
                mirror_texts,
                "3",
                ("Surface", "Curvature", "Thickness", "Refractive", "Abbe"),
            ),
            "ability_zoom_wide": _figure_page(
                mirror_texts,
                "4",
                ("Surface", "Curvature", "Thickness", "Refractive", "Abbe"),
            ),
            "ability_zoom_asphere": _figure_page(
                mirror_texts,
                "5",
                ("K", "A2", "A4"),
            ),
            "ability_zoom_meta": _figure_page(
                mirror_texts,
                "6",
                ("Fw", "Ft", "TTL", "Fno", "FOV"),
            ),
        }
        parser_profile = profile
        source_facts = _ability_zoom_two_state_source_facts(primary_html)
    elif profile == _GENIUS_FOUR_LENS_ELEVEN_PROFILE:
        assert genius_four_lens_layout is not None
        expected_page_count = genius_four_lens_layout["page_count"]
        if page_count != expected_page_count:
            raise PatentPdfRecoveryError(
                "Genius eleven-embodiment PDF page count changed: "
                f"actual={page_count} expected={expected_page_count}"
            )
        drawing_page_offset = genius_four_lens_layout["drawing_page_offset"]
        role_sheets: dict[str, int] = {}
        for embodiment, (optical_figure, asphere_figure) in enumerate(
            zip(
                _GENIUS_FOUR_LENS_ELEVEN_OPTICAL_FIGURES,
                _GENIUS_FOUR_LENS_ELEVEN_ASPHERE_FIGURES,
                strict=True,
            ),
            start=1,
        ):
            role_sheets[f"genius_optical_{embodiment}"] = (
                2 if embodiment == 1 else optical_figure
            )
            role_sheets[f"genius_asphere_{embodiment}"] = asphere_figure
        role_sheets["genius_comparison"] = 46
        role_pages = {
            role: sheet + drawing_page_offset - 1
            for role, sheet in role_sheets.items()
        }
        for role, page_index in role_pages.items():
            sheet = role_sheets[role]
            mirror_text = mirror_texts[page_index]
            if mirror_text and f"Sheet {sheet} of 48" not in re.sub(
                r"\s+", " ", mirror_text
            ):
                raise PatentPdfRecoveryError(
                    f"Genius role {role} lacks its drawing-sheet header"
                )
        parser_profile = profile
        source_facts = _genius_four_lens_eleven_source_facts(primary_html)
    elif profile == _GENIUS_NINE_LENS_ELEVEN_PROFILE:
        if page_count != 65:
            raise PatentPdfRecoveryError(
                "Genius nine-lens eleven-embodiment PDF page count is not 65"
            )
        role_pages = {}
        for embodiment in range(1, 12):
            optical_page_index = 6 + (embodiment - 1) * 4
            role_pages[f"genius_nine_eleven_optical_{embodiment}"] = optical_page_index
            role_pages[f"genius_nine_eleven_asphere_{embodiment}"] = optical_page_index + 1
        role_pages["genius_nine_eleven_comparison_1"] = 48
        role_pages["genius_nine_eleven_comparison_2"] = 49
        parser_profile = profile
        source_facts = _genius_nine_lens_eleven_source_facts(primary_html)
    elif profile == _GENIUS_EIGHT_LENS_FOURTEEN_PROFILE:
        if page_count != 64:
            raise PatentPdfRecoveryError(
                "Genius eight-lens fourteen-embodiment PDF page count is not 64"
            )
        role_pages = {}
        for embodiment in range(1, 15):
            optical_page_index = 4 + (embodiment - 1) * 3
            role_pages[f"genius_eight_fourteen_optical_{embodiment}"] = optical_page_index
            role_pages[f"genius_eight_fourteen_asphere_{embodiment}"] = (
                optical_page_index + 1
            )
        role_pages["genius_eight_fourteen_comparison_1"] = 45
        role_pages["genius_eight_fourteen_comparison_2"] = 46
        parser_profile = profile
        source_facts = _genius_eight_lens_fourteen_source_facts(primary_html)
    elif profile == _GENIUS_SEVEN_LENS_SEVEN_PROFILE:
        layout = _genius_seven_lens_seven_source_layout(primary_html)
        if page_count != layout["page_count"]:
            raise PatentPdfRecoveryError(
                "Genius seven-lens seven-example PDF page count changed: "
                f"actual={page_count} expected={layout['page_count']}"
            )
        role_pages = {}
        for example in range(1, 8):
            optical_page_index = 10 + (example - 1) * 2
            optical_role = f"genius_seven_optical_{example}"
            asphere_role = f"genius_seven_asphere_{example}"
            role_pages[optical_role] = optical_page_index
            role_pages[asphere_role] = optical_page_index + 1
            page_ocr_metadata[optical_role] = {"rapidocr_scale": 0.5}
            page_ocr_metadata[asphere_role] = {
                "rapidocr_rotation": "clockwise_90",
                "rapidocr_scale": 0.5,
            }
        role_pages["genius_seven_comparison_1"] = 24
        role_pages["genius_seven_comparison_2"] = 25
        page_ocr_metadata["genius_seven_comparison_1"] = {"rapidocr_scale": 0.5}
        page_ocr_metadata["genius_seven_comparison_2"] = {
            "rapidocr_rotation": "clockwise_90",
            "rapidocr_scale": 0.5,
        }
        parser_profile = profile
        source_facts = _genius_seven_lens_seven_source_facts(primary_html)
    elif profile == _GENIUS_FOUR_LENS_NINE_PROFILE:
        if page_count != 47:
            raise PatentPdfRecoveryError("Genius four-lens nine-embodiment PDF page count is not 47")
        role_pages = {}
        for embodiment in range(1, 10):
            optical_page_index = 4 + (embodiment - 1) * 3
            role_pages[f"genius_four_nine_optical_{embodiment}"] = optical_page_index
            role_pages[f"genius_four_nine_asphere_{embodiment}"] = optical_page_index + 1
        for comparison in range(1, 5):
            role_pages[f"genius_four_nine_comparison_{comparison}"] = 29 + comparison
        parser_profile = profile
        source_facts = _genius_four_lens_nine_source_facts(primary_html)
    elif profile == _GENIUS_FOUR_LENS_EIGHT_PROFILE:
        if page_count != 41:
            raise PatentPdfRecoveryError(
                "Genius four-lens eight-embodiment PDF page count is not 41"
            )
        role_pages = {}
        for embodiment in range(1, 9):
            optical_page_index = 12 + (embodiment - 1) * 2
            role_pages[f"genius_four_eight_optical_{embodiment}"] = optical_page_index
            role_pages[f"genius_four_eight_asphere_{embodiment}"] = optical_page_index + 1
        role_pages["genius_four_eight_comparison"] = 28
        parser_profile = profile
        source_facts = _genius_four_lens_eight_source_facts(primary_html)
    elif profile == _GENIUS_SIX_LENS_FIVE_PROFILE:
        if page_count != 34:
            raise PatentPdfRecoveryError("Genius five-embodiment PDF page count is not 34")
        role_pages = {}
        for embodiment, (optical_page_index, asphere_page_index) in enumerate(
            zip((5, 8, 11, 14, 17), (6, 9, 12, 15, 18), strict=True),
            start=1,
        ):
            role_pages[f"genius_six_optical_{embodiment}"] = optical_page_index
            role_pages[f"genius_six_asphere_{embodiment}"] = asphere_page_index
        role_pages["genius_six_comparison_1"] = 19
        role_pages["genius_six_comparison_2"] = 20
        parser_profile = profile
        source_facts = _genius_six_lens_five_source_facts(primary_html)
    elif profile == _GENIUS_SIX_LENS_NINE_PROFILE:
        if page_count not in {50, 51}:
            raise PatentPdfRecoveryError(
                "Genius nine-embodiment PDF page count is not retained 50/51 layout"
            )
        role_pages = {}
        for embodiment in range(1, 10):
            optical_page_index = 5 + (embodiment - 1) * 3
            role_pages[f"genius_six_optical_{embodiment}"] = optical_page_index
            role_pages[f"genius_six_asphere_{embodiment}"] = optical_page_index + 1
        role_pages["genius_six_comparison_1"] = 31
        role_pages["genius_six_comparison_2"] = 32
        parser_profile = profile
        source_facts = _genius_six_lens_nine_source_facts(primary_html)
    elif profile == _GENIUS_SIX_LENS_TEN_DUAL_FOCUS_PROFILE:
        if page_count != 64:
            raise PatentPdfRecoveryError(
                "Genius ten-embodiment dual-focus PDF page count is not 64"
        )
        role_pages = {}
        for embodiment in range(1, 11):
            optical_page_index = 23 + (embodiment - 1) * 2
            role_pages[f"genius_six_ten_dual_optical_{embodiment}"] = optical_page_index
            role_pages[f"genius_six_ten_dual_asphere_{embodiment}"] = (
                optical_page_index + 1
            )
        for comparison in range(1, 5):
            role_pages[f"genius_six_ten_dual_comparison_{comparison}"] = 42 + comparison
        parser_profile = profile
        source_facts = _genius_six_lens_ten_dual_focus_source_facts(primary_html)
    elif profile == _GENIUS_SIX_LENS_NINE_THREE_COMPARISON_PROFILE:
        if page_count != 48:
            raise PatentPdfRecoveryError(
                "Genius three-comparison nine-embodiment PDF page count is not 48"
            )
        role_pages = {}
        for embodiment in range(1, 10):
            optical_page_index = 5 + (embodiment - 1) * 3
            role_pages[f"genius_six_optical_{embodiment}"] = optical_page_index
            role_pages[f"genius_six_asphere_{embodiment}"] = optical_page_index + 1
        for comparison in range(1, 4):
            role_pages[f"genius_six_comparison_{comparison}"] = 30 + comparison
        parser_profile = profile
        source_facts = _genius_six_lens_nine_three_comparison_source_facts(primary_html)
    elif profile == _GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_PROFILE:
        if page_count != 50:
            raise PatentPdfRecoveryError(
                "Genius four-comparison nine-embodiment PDF page count is not 50"
            )
        role_pages = {}
        for embodiment in range(1, 10):
            optical_page_index = 5 + (embodiment - 1) * 3
            role_pages[f"genius_six_optical_{embodiment}"] = optical_page_index
            role_pages[f"genius_six_asphere_{embodiment}"] = optical_page_index + 1
        for comparison in range(1, 5):
            role_pages[f"genius_six_comparison_{comparison}"] = 30 + comparison
        parser_profile = profile
        source_facts = _genius_six_lens_nine_four_comparison_source_facts(primary_html)
    else:
        raise PatentPdfRecoveryError(f"unsupported Ability PDF profile: {profile}")
    if len(set(role_pages.values())) != len(role_pages):
        raise PatentPdfRecoveryError("Ability PDF key roles do not map to distinct pages")

    key_pages: list[tuple[int, str, str, str, list[dict[str, Any]]]] = []
    for role, page_index in sorted(role_pages.items(), key=lambda item: item[1]):
        role_ocr_metadata = page_ocr_metadata.get(role, {})
        key_pages.append(
            (
                page_index + 1,
                role,
                page_hashes[page_index],
                mirror_texts[page_index],
                _rapidocr_tokens(
                    official_images[page_index],
                    rotation=role_ocr_metadata.get(
                        "rapidocr_rotation",
                        rapidocr_rotation,
                    ),
                    scale=role_ocr_metadata.get("rapidocr_scale"),
                ),
            )
        )
    parser_input = _canonical_parser_input(
        publication_id=publication_id,
        page_count=page_count,
        key_pages=key_pages,
        profile=parser_profile,
        source_facts=source_facts,
        rapidocr_rotation=rapidocr_rotation,
        page_ocr_metadata=page_ocr_metadata or None,
    )
    from importlib.metadata import version

    return PatentPdfOcrRecovery(
        publication_id=publication_id,
        official_pdf=official_pdf,
        official_pdf_url=official_url,
        mirror_pdf=mirror_pdf,
        mirror_pdf_url=mirror_url,
        parser_input=parser_input,
        page_count=page_count,
        page_image_sha256=tuple(page_hashes),
        key_page_numbers=tuple(page_index + 1 for page_index in role_pages.values()),
        pypdf_version=pypdf.__version__,
        rapidocr_version=version("rapidocr-onnxruntime"),
    )
