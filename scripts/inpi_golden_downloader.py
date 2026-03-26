"""
INPI Golden Case Downloader
============================
Télécharge des bilans réels depuis l'API INPI et génère des golden cases
pour ConfiDoc (PDF + valeurs attendues via bilans-saisis).

Usage:
    python scripts/inpi_golden_downloader.py --output golden/inpi_samples/ --count 50

Credentials: INPI_USER / INPI_PASS (env vars) ou --user / --password CLI args.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

BASE_URL = "https://registre-national-entreprises.inpi.fr/api"

# CERFA codes → champs ConfiDoc pour bilans type C et S
CERFA_TO_CONFID0C_BILAN: dict[str, str] = {
    # Actif (page 1 type C / page 1 type S)
    "BJ": "immobilisations",
    "CF": "disponibilites",
    "CO": "total_actif",
    # Passif (page 2 type C / page 1 type S)
    "DA": "capital_social",
    "DI": "resultat_exercice",
    "DL": "capitaux_propres",
    "EE": "total_passif",
    "EC": "dettes_financieres",
    # Créances (page 1 type C)
    "BX": "creances",
}

CERFA_TO_CONFID0C_CR: dict[str, str] = {
    # Compte de résultat (page 3 type C / page 2 type S)
    "FJ": "chiffre_affaires",
    "GG": "resultat_exploitation",
    "GV": "resultat_courant",
    "HN": "resultat_net",
    "FL": "charges_externes",
}

# Quelques SIRENs de sociétés publiques connues pour amorcer les téléchargements
# (grandes entreprises cotées = données publiques, formats variés de logiciels compta)
SEED_SIRENS = [
    "552032534",  # Total Energies
    "552081317",  # Carrefour
    "326817685",  # LVMH
    "542107651",  # BNP Paribas
    "382241047",  # L'Oréal
    "775672272",  # Société Générale
    "744000945",  # AXA
    "572028637",  # Air France-KLM
    "380129866",  # Michelin
    "542054180",  # Renault
    # PME variées (formats comptables différents)
    "493455042",
    "804326838",
    "812382590",
    "751600000",
    "450584994",
    "523916100",
    "817490571",
    "842327019",
]


def login(username: str, password: str) -> str:
    resp = httpx.post(
        f"{BASE_URL}/sso/login",
        json={"username": username, "password": password},
        timeout=15,
    )
    resp.raise_for_status()
    token = resp.json().get("token")
    if not token:
        raise RuntimeError(f"Login failed: {resp.json()}")
    return token


def get_attachments(siren: str, headers: dict) -> dict:
    resp = httpx.get(f"{BASE_URL}/companies/{siren}/attachments", headers=headers, timeout=15)
    if resp.status_code == 404:
        return {"bilans": [], "bilansSaisis": []}
    resp.raise_for_status()
    return resp.json()


def download_pdf(doc_id: str, headers: dict) -> bytes | None:
    resp = httpx.get(f"{BASE_URL}/bilans/{doc_id}/download", headers=headers, timeout=30)
    if resp.status_code != 200:
        return None
    return resp.content


def get_bilan_saisi(doc_id: str, headers: dict) -> dict | None:
    resp = httpx.get(f"{BASE_URL}/bilans-saisis/{doc_id}", headers=headers, timeout=15)
    if resp.status_code != 200:
        return None
    return resp.json()


def cerfa_pages_to_fields(pages: list[dict], type_bilan: str) -> dict[str, float]:
    """Convertit les pages CERFA en champs ConfiDoc."""
    fields: dict[str, float] = {}
    for page in pages:
        page_num = page.get("numero")
        liasses = page.get("liasses") or []
        for item in liasses:
            code = item.get("code", "")
            # m1 = valeur exercice N (colonne principale)
            raw = item.get("m1") or ""
            if not raw or raw.strip("-0") == "":
                continue
            try:
                val = float(raw.replace(" ", "").replace("\u00a0", ""))
            except ValueError:
                continue
            if val == 0.0:
                continue
            # Bilan
            if page_num in (1, 2) and code in CERFA_TO_CONFID0C_BILAN:
                fields[CERFA_TO_CONFID0C_BILAN[code]] = val
            # Compte de résultat
            elif page_num in (3, 4) and code in CERFA_TO_CONFID0C_CR:
                fields[CERFA_TO_CONFID0C_CR[code]] = val
            # Type S: bilan sur page 1, CR sur page 2
            elif type_bilan == "S":
                if page_num == 1 and code in CERFA_TO_CONFID0C_BILAN:
                    fields[CERFA_TO_CONFID0C_BILAN[code]] = val
                elif page_num == 2 and code in CERFA_TO_CONFID0C_CR:
                    fields[CERFA_TO_CONFID0C_CR[code]] = val
    return fields


def pick_doc_type(type_bilan: str, cerfa_fields: dict) -> str:
    """Détermine le doc_type ConfiDoc depuis le typeBilan CERFA."""
    if "chiffre_affaires" in cerfa_fields or "resultat_net" in cerfa_fields:
        return "compte_resultat"
    return "bilan"


def process_siren(
    siren: str,
    headers: dict,
    output_dir: Path,
    golden_cases: list[dict],
    max_per_siren: int = 2,
) -> int:
    """Traite un SIREN : télécharge PDFs + bilans-saisis, génère golden cases."""
    try:
        data = get_attachments(siren, headers)
    except Exception as e:
        print(f"  [{siren}] attachments error: {e}")
        return 0

    # Index bilans-saisis par id pour matching rapide
    saisis_by_id: dict[str, dict] = {}
    for bs in (data.get("bilansSaisis") or []):
        if not bs.get("deleted") and bs.get("id"):
            saisis_by_id[bs["id"]] = bs

    # Bilans PDF publics, non supprimés, types C ou S
    bilans_pdf = [
        b for b in (data.get("bilans") or [])
        if not b.get("deleted")
        and b.get("confidentiality") == "Public"
        and b.get("typeBilan") in ("C", "S")
    ]

    generated = 0
    for bilan in bilans_pdf[:max_per_siren]:
        doc_id = bilan.get("id")
        date_cloture = bilan.get("dateCloture", "")[:10]
        type_bilan = bilan.get("typeBilan", "C")
        denom = bilan.get("denomination", siren)[:40].replace("/", "_").replace(" ", "_")

        # Cherche le bilan-saisi correspondant (même siren + même dateCloture)
        saisi = None
        for bs in saisis_by_id.values():
            if bs.get("dateCloture", "")[:10] == date_cloture:
                saisi = bs
                break

        if saisi is None:
            # Pas de données structurées → golden case sans expected_values
            continue

        # Extrait les champs depuis les pages CERFA
        pages = []
        try:
            pages = (
                saisi.get("bilanSaisi", {})
                .get("bilan", {})
                .get("detail", {})
                .get("pages", [])
            )
        except Exception:
            pass

        if not pages:
            continue

        cerfa_fields = cerfa_pages_to_fields(pages, type_bilan)
        if len(cerfa_fields) < 2:
            continue

        # Télécharge le PDF
        pdf_bytes = download_pdf(doc_id, headers)
        if not pdf_bytes or len(pdf_bytes) < 1000:
            continue

        # Sauvegarde le PDF
        pdf_name = f"inpi_{siren}_{date_cloture}_{type_bilan}_{doc_id[:8]}.pdf"
        pdf_path = output_dir / "pdfs" / pdf_name
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(pdf_bytes)

        doc_type = pick_doc_type(type_bilan, cerfa_fields)
        case_id = f"inpi_{siren}_{date_cloture}_{doc_type}"

        golden_cases.append({
            "id": case_id,
            "doc_type": doc_type,
            "source": "inpi_api",
            "siren": siren,
            "denomination": denom,
            "date_cloture": date_cloture,
            "type_bilan": type_bilan,
            "pdf_file": str(pdf_path.relative_to(output_dir.parent)),
            "cerfa_fields": cerfa_fields,
            "note": "Golden case auto-généré via API INPI — valeurs issues bilans-saisis CERFA",
        })

        print(f"  [{siren}] ✓ {doc_type} {date_cloture} — {len(cerfa_fields)} champs CERFA — {len(pdf_bytes)//1024}KB")
        generated += 1
        time.sleep(0.2)  # politesse API

    return generated


def main() -> None:
    parser = argparse.ArgumentParser(description="INPI Golden Case Downloader")
    parser.add_argument("--output", default="golden/inpi_samples", help="Dossier de sortie")
    parser.add_argument("--count", type=int, default=50, help="Nombre de cas cibles")
    parser.add_argument("--user", default=os.environ.get("INPI_USER", ""))
    parser.add_argument("--password", default=os.environ.get("INPI_PASS", ""))
    args = parser.parse_args()

    if not args.user or not args.password:
        print("INPI_USER et INPI_PASS requis (env vars ou --user/--password)")
        sys.exit(1)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Authentification INPI...")
    token = login(args.user, args.password)
    headers = {"Authorization": f"Bearer {token}"}
    print("Token OK\n")

    golden_cases: list[dict] = []
    total = 0

    for siren in SEED_SIRENS:
        if total >= args.count:
            break
        print(f"→ SIREN {siren}")
        n = process_siren(siren, headers, output_dir, golden_cases, max_per_siren=3)
        total += n
        time.sleep(0.3)

    # Sauvegarde l'index des golden cases
    index_path = output_dir / "golden_cases_inpi.json"
    index_path.write_text(
        json.dumps({"count": len(golden_cases), "cases": golden_cases}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\n✓ {len(golden_cases)} golden cases générés → {index_path}")
    print(f"  PDFs → {output_dir / 'pdfs'}")


if __name__ == "__main__":
    main()
