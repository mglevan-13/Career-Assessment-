"""Build careers.json from BLS sources (static site friendly).

Notes:
- BLS does not collect starting salaries. We use the 25th percentile wage as a conservative
  "starting pay proxy" from OEWS wage distributions.
- This script downloads public BLS files and generates careers.json for your static site.
"""

import re, json
import pandas as pd
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

OOH_XML_URL = "https://www.bls.gov/ooh/xml-compilation.xml"
OEWS_MI_PAGE = "https://www.bls.gov/oes/2023/may/oes_mi.htm"  # update year as needed

# Update these MI tuition+fees values from NCES Table 330.20 each year if you want.
MI_PUBLIC_2YR = 0
MI_PUBLIC_4YR = 0

TARGET_TITLES = [
  "Software Developers",
  "Registered Nurses",
  "Accountants and Auditors",
  "Elementary School Teachers, Except Special Education",
  "Electricians",
  "Plumbers, Pipefitters, and Steamfitters",
  "Web Developers",
  "Computer Systems Analysts",
  "Physical Therapist Assistants",
  "Occupational Therapy Assistants",
  "Dental Hygienists",
  "Radiologic Technologists and Technicians",
  "Project Management Specialists",
  "Graphic Designers",
  "Market Research Analysts and Marketing Specialists",
  "Construction Managers",
  "Carpenters",
  "Firefighters",
  "Police and Sheriff's Patrol Officers",
  "Environmental Scientists and Specialists, Including Health"
]

def norm(s: str) -> str:
  return re.sub(r"\s+"," ",s.lower().strip())

def parse_ooh(xml_text: str):
  root = ET.fromstring(xml_text)
  out = {}
  # Many elements are namespaced; strip namespaces.
  for occ in root.findall(".//occupation"):
    title = occ.findtext("title") or ""
    title = title.strip()
    if not title:
      continue
    summary = occ.findtext("summary")
    if summary:
      summary = re.sub(r"\s+"," ",summary.strip())
    edu = occ.findtext("education") or occ.findtext("entry_level_education") or ""
    edu = re.sub(r"\s+"," ",edu.strip()) if edu else None
    url = occ.findtext("url") or ""
    url = url.strip() if url else None
    out[norm(title)] = {"title": title, "summary": summary, "entry_education": edu, "ooh_url": url}
  return out

def find_oews_xls_url():
  html = requests.get(OEWS_MI_PAGE, timeout=60).text
  soup = BeautifulSoup(html, "html.parser")
  for a in soup.select("a[href]"):
    href = a["href"]
    if href.lower().endswith((".xls",".xlsx")):
      return requests.compat.urljoin(OEWS_MI_PAGE, href)
  raise RuntimeError("Could not find OEWS XLS link.")

def load_oews(xls_url: str):
  df = pd.read_excel(xls_url)
  # Normalize columns
  df.columns = [norm(str(c)) for c in df.columns]
  title_col = next((c for c in df.columns if "occupation title" in c), df.columns[0])

  # Try common names
  p25_col = next((c for c in df.columns if "annual 25th percentile" in c or ("25" in c and "annual" in c)), None)
  med_col = next((c for c in df.columns if "annual median" in c or ("median" in c and "annual" in c)), None)

  out = {}
  for _, r in df.iterrows():
    t = r.get(title_col)
    if not isinstance(t, str): 
      continue
    out[norm(t)] = {
      "p25": float(r[p25_col]) if p25_col and pd.notna(r[p25_col]) else None,
      "median": float(r[med_col]) if med_col and pd.notna(r[med_col]) else None
    }
  return out

def edu_cost(entry_edu: str):
  e = (entry_edu or "").lower()
  if not e: return None
  if "associate" in e:
    return {"years":2,"total_tuition_fees":MI_PUBLIC_2YR*2,"note":"Community college estimate (tuition+fees only)."}
  if "bachelor" in e:
    return {"years":4,"total_tuition_fees":MI_PUBLIC_4YR*4,"note":"Public 4-year in-state estimate (tuition+fees only)."}
  if "master" in e:
    return {"years":6,"total_tuition_fees":MI_PUBLIC_4YR*6,"note":"Very rough estimate (tuition+fees only)."}
  if "doctoral" in e or "professional" in e:
    return {"years":8,"total_tuition_fees":MI_PUBLIC_4YR*8,"note":"Very rough estimate (tuition+fees only)."}
  if "postsecondary nondegree" in e:
    return {"years":1,"total_tuition_fees":MI_PUBLIC_2YR,"note":"Certificate/trade estimate (tuition+fees only)."}
  if "high school" in e or "no formal" in e:
    return {"years":0,"total_tuition_fees":0,"note":"No college required; training may still cost money."}
  return None

def main():
  print("Downloading OOH XML…")
  xml = requests.get(OOH_XML_URL, timeout=120).text
  ooh = parse_ooh(xml)

  print("Downloading OEWS wage percentiles XLS…")
  xls_url = find_oews_xls_url()
  wages = load_oews(xls_url)

  careers = []
  for title in TARGET_TITLES:
    k = norm(title)
    rec = ooh.get(k, {"title": title, "summary": None, "entry_education": None, "ooh_url": None})
    w = wages.get(k, {"p25": None, "median": None})
    careers.append({
      "title": rec["title"],
      "bls": {
        "summary": rec["summary"],
        "entry_education": rec["entry_education"],
        "ooh_url": rec["ooh_url"] or f"https://www.bls.gov/ooh/occupation-finder.htm?search={requests.utils.quote(rec['title'])}"
      },
      "pay": {
        "starting_proxy_annual": w["p25"],
        "median_annual": w["median"]
      },
      "education_cost": edu_cost(rec["entry_education"])
    })

  with open("careers.json","w",encoding="utf-8") as f:
    json.dump({"version":"bls_static_v1","careers":careers}, f, ensure_ascii=False, indent=2)

  print("Wrote careers.json with", len(careers), "careers")

if __name__ == "__main__":
  main()