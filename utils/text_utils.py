import re

def get_qty(name):

    name = str(name).lower()

    match = re.search(r'(\d+)ea', name)

    if match:
        return int(match.group(1))

    return 1


def clean_v(v):

    v = str(v).replace('청호_', '')

    for k in ["수도권", "대전", "대구", "부산", "경남", "광주", "전주", "강원"]:
        if k in v:
            return k

    return v