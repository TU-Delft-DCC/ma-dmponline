import re
from datetime import datetime
import hashlib
from bs4 import BeautifulSoup
import sys


def print(text):
    sys.stdout.write(str(text) + "\n")


def get_datetime(dt_string):
    return datetime.strptime(dt_string, "%Y-%m-%dT%H:%M:%S")


def remove_special_chars_from_list(items):
    clean_items = []
    if u"\xa0" in items:
        items.remove(u"\xa0")
    if "\xa0" in items:
        items.remove("\xa0")
    for location in items:
        location = location.strip()
        location = location.replace(u"\xa0", u"")
        if location != "":
            clean_items.append(location)

    items = set(clean_items)

    return items


def html_table_to_list(html_table):
    html_table = html_table.replace("\n", "").replace("\r", "")

    soup = BeautifulSoup(html_table, "lxml")
    table = soup.find("table")

    output_rows = []
    for table_row in table.findAll("tr"):
        columns = table_row.findAll("td")
        output_row = []
        for column in columns:
            output_row.append(column.text)
        output_rows.append(output_row)

    rlist = []
    for row in output_rows[1:]:
        columns = {}
        for i in range(len(output_rows[0])):
            columns[output_rows[0][i]] = row[i]
        rlist.append(columns)

    return rlist


def clean_html(raw_html):
    cleaner = re.compile("<.*?>|&([a-z0-9]+|#[0-9]{1,6}|#x[0-9a-f]{1,6});")
    clean_text = re.sub(cleaner, "", raw_html)
    return clean_text


def get_md5(text):
    result = hashlib.md5(text.encode())
    return result.hexdigest()
