#!/usr/bin/env python3
"""
Tableau de pilotage extraction - Métriques par type de document.

Usage:
    python -m app.services.extraction_quality_dashboard --golden
    python -m app.services.extraction_quality_dashboard --docs path/to/docs/
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.services.structured_dataset_service import (
    _extract_bilan,
    _extract_compte_resultat,
    _extract_2072,
    _extract_releve_bancaire_fields,
    _extract_etat_immobilisations,
    _quality_bilan,
    _quality_compte_resultat,
    _quality_2072,
)


# Quality wrappers pour uniformiser les signatures
def _quality_2072_wrapper(fields: dict) -> dict:
    """Wrapper pour _quality_2072 avec valeurs par défaut."""
    # Appel simplifié - les tables et text ne sont pas critiques pour le dashboard
    return _quality_2072(fields, {}, "")


# Mapping des types d'extracteurs
EXTRACTORS = {
    "bilan": (_extract_bilan, _quality_bilan),
    "compte_resultat": (_extract_compte_resultat, _quality_compte_resultat),
    "fiscal_2072": (_extract_2072, _quality_2072_wrapper),
    "releve_bancaire": (_extract_releve_bancaire_fields, lambda f: {"ready_for_ai_core": True}),
    "immobilisations": (_extract_etat_immobilisations, lambda f: {"ready_for_ai_core": True}),
}

# Champs critiques par type
CRITICAL_FIELDS = {
    "bilan": ["total_actif", "total_passif", "capitaux_propres", "dettes_financieres", "dettes_fournisseurs", "resultat_exercice"],
    "compte_resultat": ["total_produits", "total_charges", "resultat_net", "resultat_exploitation"],
    "fiscal_2072": ["revenus_bruts", "frais_charges", "interets_emprunts", "revenu_net"],
    "releve_bancaire": ["solde_initial", "solde_final", "total_credits", "total_debits"],
    "immobilisations": ["total_brut", "total_amortissements", "total_net"],
}


class ExtractionQualityDashboard:
    """Dashboard de métriques extraction par type de document."""

    def __init__(self):
        self.metrics: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "total_docs": 0,
            "core_ready": 0,
            "full_ready": 0,
            "needs_review": 0,
            "fields": defaultdict(lambda: {
                "extracted": 0,
                "missing": 0,
                "by_source": defaultdict(int),
            }),
            "suspicious_fields_count": defaultdict(int),
            "sources_distribution": defaultdict(int),
            "quality_flags": defaultdict(int),
        })

    def analyze_document(self, doc_type: str, text: str, expected: dict | None = None) -> dict:
        """Analyse un document et retourne les métriques."""
        if doc_type not in EXTRACTORS:
            return {"error": f"Type {doc_type} non supporté"}

        extractor, quality_fn = EXTRACTORS[doc_type]
        fields = extractor(text)
        quality = quality_fn(fields)

        # Métriques globales
        m = self.metrics[doc_type]
        m["total_docs"] += 1
        
        if quality.get("ready_for_ai_core"):
            m["core_ready"] += 1
        if quality.get("ready_for_ai"):
            m["full_ready"] += 1
        if quality.get("needs_review"):
            m["needs_review"] += 1

        # Quality flags
        for flag in quality.get("quality_flags", []):
            m["quality_flags"][flag] += 1

        # Suspicious fields
        for sf in quality.get("suspicious_fields", []):
            m["suspicious_fields_count"][sf] += 1

        # Analyse par champ
        critical = CRITICAL_FIELDS.get(doc_type, [])
        for field_name in critical:
            field_data = fields.get(field_name, {})
            value = field_data.get("value")
            source = field_data.get("source_hint", "missing")

            fm = m["fields"][field_name]
            if value is not None:
                fm["extracted"] += 1
            else:
                fm["missing"] += 1
            fm["by_source"][source] += 1
            m["sources_distribution"][source] += 1

        # Précision si expected fourni
        precision = None
        if expected:
            precision = self._calculate_precision(fields, expected, critical)

        return {
            "doc_type": doc_type,
            "quality": quality,
            "precision": precision,
            "fields_count": len([f for f in fields.values() if f.get("value") is not None]),
        }

    def _calculate_precision(self, fields: dict, expected: dict, critical: list) -> dict:
        """Calcule la précision vs expected."""
        correct = 0
        total = 0
        errors = []

        for field_name in critical:
            expected_val = expected.get(field_name)
            actual_val = fields.get(field_name, {}).get("value")

            if expected_val is not None:
                total += 1
                if actual_val is not None and abs(float(actual_val) - float(expected_val)) < 1.0:
                    correct += 1
                else:
                    errors.append({
                        "field": field_name,
                        "expected": expected_val,
                        "actual": actual_val,
                    })

        return {
            "correct": correct,
            "total": total,
            "rate": correct / total if total > 0 else 0,
            "errors": errors,
        }

    def generate_report(self) -> dict:
        """Génère le rapport final."""
        report = {}
        
        for doc_type, m in self.metrics.items():
            total = m["total_docs"]
            if total == 0:
                continue

            # Taux globaux
            report[doc_type] = {
                "total_docs": total,
                "rates": {
                    "core_ready": round(m["core_ready"] / total * 100, 1),
                    "full_ready": round(m["full_ready"] / total * 100, 1),
                    "needs_review": round(m["needs_review"] / total * 100, 1),
                },
                # Top champs suspects
                "top_suspicious_fields": sorted(
                    m["suspicious_fields_count"].items(),
                    key=lambda x: x[1],
                    reverse=True,
                )[:5],
                # Distribution sources
                "sources_distribution": dict(m["sources_distribution"]),
                # Quality flags fréquents
                "top_quality_flags": sorted(
                    m["quality_flags"].items(),
                    key=lambda x: x[1],
                    reverse=True,
                )[:5],
                # Performance par champ critique
                "critical_fields": {},
            }

            # Analyse par champ
            critical = CRITICAL_FIELDS.get(doc_type, [])
            for field_name in critical:
                fm = m["fields"][field_name]
                field_total = fm["extracted"] + fm["missing"]
                if field_total > 0:
                    report[doc_type]["critical_fields"][field_name] = {
                        "extraction_rate": round(fm["extracted"] / field_total * 100, 1),
                        "missing_rate": round(fm["missing"] / field_total * 100, 1),
                        "sources": dict(fm["by_source"]),
                    }

        return report

    def print_report(self):
        """Affiche le rapport formaté."""
        report = self.generate_report()
        
        print("=" * 80)
        print("TABLEAU DE PILOTAGE - EXTRACTION CONFI DOC")
        print("=" * 80)
        print()

        for doc_type, data in report.items():
            print(f"📄 {doc_type.upper()}")
            print("-" * 40)
            print(f"  Documents analysés: {data['total_docs']}")
            print(f"  Core Ready:         {data['rates']['core_ready']}%")
            print(f"  Full Ready:         {data['rates']['full_ready']}%")
            print(f"  Needs Review:       {data['rates']['needs_review']}%")
            print()

            # Top champs suspects
            if data['top_suspicious_fields']:
                print("  ⚠️  Top champs suspects:")
                for field, count in data['top_suspicious_fields']:
                    print(f"      {field}: {count} fois")
                print()

            # Sources
            if data['sources_distribution']:
                print("  📊 Sources d'extraction:")
                for source, count in sorted(data['sources_distribution'].items(), key=lambda x: -x[1]):
                    pct = round(count / data['total_docs'] * 100, 1)
                    print(f"      {source}: {count} ({pct}%)")
                print()

            # Champs critiques faibles
            weak_fields = [
                (name, info) for name, info in data['critical_fields'].items()
                if info['extraction_rate'] < 90
            ]
            if weak_fields:
                print("  🔴 Champs critiques à améliorer (< 90%):")
                for name, info in sorted(weak_fields, key=lambda x: x[1]['extraction_rate']):
                    print(f"      {name}: {info['extraction_rate']}% (sources: {list(info['sources'].keys())})")
                print()

            print()

        print("=" * 80)


def analyze_golden_set(golden_path: Path = Path("golden/cases")):
    """Analyse le golden set complet."""
    dashboard = ExtractionQualityDashboard()

    for type_dir in golden_path.iterdir():
        if not type_dir.is_dir():
            continue

        doc_type = type_dir.name
        print(f"Analyse {doc_type}...")

        for case_dir in type_dir.iterdir():
            if not case_dir.is_dir():
                continue

            input_file = case_dir / "input.txt"
            expected_file = case_dir / "expected.min.json"

            if not input_file.exists():
                continue

            text = input_file.read_text()
            expected = None
            if expected_file.exists():
                expected = json.loads(expected_file.read_text())

            dashboard.analyze_document(doc_type, text, expected)

    return dashboard


def main():
    """Point d'entrée CLI."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Tableau de pilotage extraction")
    parser.add_argument("--golden", action="store_true", help="Analyser le golden set")
    parser.add_argument("--output", type=str, help="Fichier JSON de sortie")
    args = parser.parse_args()

    if args.golden:
        print("Analyse du golden set...")
        dashboard = analyze_golden_set()
        dashboard.print_report()

        if args.output:
            report = dashboard.generate_report()
            Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False))
            print(f"\nRapport sauvegardé: {args.output}")
    else:
        print("Usage: python -m app.services.extraction_quality_dashboard --golden")
        print("       python -m app.services.extraction_quality_dashboard --golden --output report.json")


if __name__ == "__main__":
    main()
