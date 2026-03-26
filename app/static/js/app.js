let accessToken = "";
let currentDocs = [];
let docDetectionMap = {};
let docQualityMap = {};
let lastAnonDocId = null;
let lastAnonText = "";
let lastOriginalDocId = null;
let lastOriginalText = "";
let previewMode = "anon"; // "anon" | "beforeafter"
let docExtractionDetails = {};
let statusSummaryDays = 30;
let lastActiveDocId = null;
let docFilterSearch = "";
let docFilterStatus = "";

const $ = id => document.getElementById(id);
const previewOut = $("previewOutput");
const maskedOut = $("maskedOutput");
const apiOut = $("apiOutput");
const docList = $("docList");
const toastBox = $("toastContainer");
const stageText = $("stageText");

function setStage(stage, message) {
  document.querySelectorAll("[data-stage]").forEach(el => {
    el.classList.toggle("active", el.getAttribute("data-stage") === stage);
  });
  if (stageText) stageText.textContent = message || "";
}

function toast(msg, type="info") {
  const icons = {success:"✅",error:"❌",info:"ℹ️"};
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.innerHTML = `<span class="toast-icon">${icons[type]||"ℹ️"}</span><span>${msg}</span>`;
  toastBox.appendChild(el);
  setTimeout(() => { el.classList.add("removing"); setTimeout(() => el.remove(), 300); }, 4000);
}

function setActionBusy(btn, busy, labelWhenBusy = "Traitement...") {
  if (!btn) return;
  if (busy) {
    if (!btn.dataset.originalText) btn.dataset.originalText = btn.textContent || "";
    btn.disabled = true;
    btn.textContent = labelWhenBusy;
  } else {
    btn.disabled = false;
    if (btn.dataset.originalText) btn.textContent = btn.dataset.originalText;
  }
}

function showApi(data) { apiOut.textContent = JSON.stringify(data, null, 2); }

function downloadJsonFile(filename, data) {
  try {
    const blob = new Blob([JSON.stringify(data, null, 2)], {type: "application/json;charset=utf-8"});
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    toast("Impossible de télécharger le fichier", "error");
  }
}

function triggerBlobDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Safari peut annuler le download si on revoke immédiatement.
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

function highlightTags(text) {
  if (!text) return "Aucune donnée.";
  const map = {"EMAIL":"tag-email","PHONE":"tag-phone","PERSON":"tag-person","ADDRESS":"tag-address","CITY":"tag-city"};
  return text.replace(/\[(\w+)\]/g, (m, tag) => {
    const cls = map[tag.toUpperCase()] || "tag-default";
    return `<span class="tag ${cls}">${m}</span>`;
  });
}

function showPreview(text) { previewOut.innerHTML = highlightTags(text); }

function currentDocTypeRequested() {
  const el = $("docTypeSelect");
  return (el && el.value) ? el.value : "auto";
}

function confidenceLabel(v) {
  const n = Number(v || 0);
  if (n >= 0.75) return "élevée";
  if (n >= 0.5) return "moyenne";
  return "faible";
}

function showAiSummaryCard(data) {
  const s = data && data.summary ? data.summary : {};
  const summarySource = (data && data.summary_source) || "";
  const modeFallback = summarySource.startsWith("fallback_");
  const fallbackError = modeFallback && data.ollama_validation && data.ollama_validation.error
    ? data.ollama_validation.error : null;
  const modeText = modeFallback ? "Mode : synthèse de secours" : `Mode : synthèse assistée (${data.provider || "IA"})`;
  const modeClass = modeFallback ? "fallback" : "ok";
  const conf = Number(s.confiance_globale || 0);
  const points = Array.isArray(s.points_cles) ? s.points_cles : [];
  const alerts = Array.isArray(s.anomalies_ou_alertes) ? s.anomalies_ou_alertes : [];
  const questions = Array.isArray(s.questions_de_revue) ? s.questions_de_revue : [];
  const resume = s.resume_executif || "Synthèse générée avec prudence à partir des données disponibles. Une revue humaine reste recommandée.";
  const q = data && data.quality_snapshot ? data.quality_snapshot : {};
  const docStatus = q.ready_for_ai ? "Prêt IA" : (q.needs_review ? "À revoir" : "En analyse");
  const suspiciousFields = Array.isArray(q.suspicious_fields) ? q.suspicious_fields : [];
  const suspiciousHtml = suspiciousFields.length
    ? `<div class="ai-status" style="color:var(--amber)">⚠️ Champs calculés/fallback : <b>${suspiciousFields.join(", ")}</b></div>`
    : `<div class="ai-status" style="color:#34d399">✓ Tous les champs sont lus directement</div>`;
  const listHtml = arr => arr.map(x => `<li>${String(x)}</li>`).join("");
  const suspiciousText = suspiciousFields.length
    ? `Champs calculés/fallback: ${suspiciousFields.join(", ")}`
    : "Tous les champs sont lus directement";
  const summaryTextForCopy = [
    "Synthèse IA",
    `Mode: ${modeFallback ? "synthèse de secours" : "synthèse assistée"}`,
    `Confiance: ${confidenceLabel(conf)} (${Math.round(conf * 100)}%)`,
    `Statut du document: ${docStatus}`,
    suspiciousText,
    "",
    `Résumé exécutif: ${resume}`,
    "",
    "Points clés:",
    ...points.map(p => `- ${p}`),
    "",
    "Alertes:",
    ...alerts.map(a => `- ${a}`),
    "",
    "Questions de revue:",
    ...questions.map(q => `- ${q}`),
  ].join("\n");
  previewOut.innerHTML = `
    <div class="ai-summary">
      <div class="ai-head">
        <div class="ai-tools">
          <div class="ai-mode ${modeClass}">${modeText}</div>
          <button class="btn-act" id="copyAiSummaryBtn">Copier la synthèse</button>
        </div>
        <div class="ai-confidence">Confiance : <b>${confidenceLabel(conf)}</b> (${Math.round(conf * 100)}%)</div>
      </div>
      <div class="ai-status">Statut du document : <b>${docStatus}</b></div>
      ${suspiciousHtml}
      ${fallbackError ? `<div class="ai-status" style="color:var(--amber);font-size:12px">⚠️ Erreur LLM : ${escapeHtml(fallbackError)}</div>` : ""}
      <div class="ai-security">Synthèse générée à partir de données anonymisées uniquement.</div>
      <div class="ai-block">
        <div class="ai-title">Résumé exécutif</div>
        <div>${resume}</div>
      </div>
      <div class="ai-block">
        <div class="ai-title">Points clés</div>
        <ul class="ai-list">${listHtml(points)}</ul>
      </div>
      <div class="ai-block">
        <div class="ai-title">Alertes</div>
        <ul class="ai-list">${listHtml(alerts)}</ul>
      </div>
      <div class="ai-block">
        <div class="ai-title">Questions de revue</div>
        <ul class="ai-list">${listHtml(questions)}</ul>
      </div>
    </div>`;
  const copyBtn = $("copyAiSummaryBtn");
  if (copyBtn) {
    copyBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(summaryTextForCopy);
        toast("Synthèse copiée", "success");
      } catch {
        toast("Copie impossible", "error");
      }
    });
  }
  switchTab("analyse");
}
function escapeHtml(s) {
  if (s === null || s === undefined) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function setPreviewMode(mode) {
  previewMode = mode;
  const btnAnon = $("modeAnonOnly");
  const btnBA = $("modeBeforeAfter");
  if (btnAnon) btnAnon.classList.toggle("active", mode === "anon");
  if (btnBA) btnBA.classList.toggle("active", mode === "beforeafter");
}

function showBeforeAfter(originalText, anonymizedText) {
  previewOut.innerHTML = `
    <div class="split-view">
      <div class="split-pane">
        <div class="split-title">Avant (original)</div>
        <div class="split-content">${escapeHtml(originalText)}</div>
      </div>
      <div class="split-pane">
        <div class="split-title">Après (anonymisé)</div>
        <div class="split-content">${highlightTags(anonymizedText)}</div>
      </div>
    </div>
  `;
}

async function refreshMaskedSummary(docId) {
  if (!docId) return;
  try {
    const {res, data} = await api(`/api/v1/documents/${docId}/proof`);
    if (!res.ok) return;

    const types = data && data.detections_entity_types_count ? data.detections_entity_types_count : {};
    const maskedTotal = data && typeof data.detections_count === "number" ? data.detections_count : 0;

    // Dataset quality for the "à revoir" card (no raw text).
    const qRes = await api(`/api/v1/documents/${docId}/dataset-summary`);
    const quality = qRes.data && qRes.data.quality ? qRes.data.quality : {};
    const experience = qRes.data && qRes.data.experience ? qRes.data.experience : null;
    const experienceHeadline = experience && experience.headline_fr ? experience.headline_fr : "";
    const experienceSeg = experience && experience.segmentation_note_fr ? experience.segmentation_note_fr : "";
    const accountingCount = qRes.data ? qRes.data.accounting_records_count : null;
    const requested = currentDocTypeRequested();
    const sRes = await api(`/api/v1/documents/${docId}/export-structured-dataset?doc_type=${encodeURIComponent(requested)}`);
    const sData = sRes.data || {};
    const sQ = sData.quality || {};
    const criticalMissing = Array.isArray(sQ.critical_missing_fields) ? sQ.critical_missing_fields : [];
    const provSeg = sData.provenance && sData.provenance.text_segmentation;
    const extractionDetails = {
      routing_requested: requested,
      routing_selected: sData.detected_doc_type || "unknown",
      extractor_selected: (sData.provenance && sData.provenance.extractor_name) || "unknown",
      routing_confidence: typeof sData.routing_confidence === "number" ? sData.routing_confidence : null,
      doc_type: sData.doc_type || "unknown",
      text_segmentation: provSeg || null,
    };
    docExtractionDetails[docId] = extractionDetails;

    const qualityFlagsCount = Array.isArray(quality.quality_flags) ? quality.quality_flags.length : 0;

    function fuseCategory(entityType) {
      const t = entityType || "";
      if (t.startsWith("person_") || t === "company_legal_name") return "Noms de personnes";
      if (t === "email") return "Email";
      if (t.startsWith("phone_")) return "Téléphone";
      if (t === "iban" || t === "iban_compact" || t === "bic" || t === "bank_account_code_label") return "Identifiants bancaires";
      if (t === "siret" || t === "siren" || t === "vat_fr") return "Identifiants entreprise & fiscalité";
      if (t === "nss") return "Identifiant personnel";
      if (t.startsWith("address_") || t === "postal_city") return "Adresses et données de localisation";
      if (t.startsWith("date_")) return "Dates";
      if (t === "invoice_number" || t === "invoice_identity_block") return "Références documentaires";
      if (t === "labeled_sensitive_value") return "Valeurs sensibles (libellé : valeur)";
      if (t.startsWith("amount_")) return "Montants";
      if (t === "country") return "Pays";
      return "Autre";
    }

    const fused = {};
    for (const [k,v] of Object.entries(types)) {
      const cat = fuseCategory(k);
      fused[cat] = (fused[cat] || 0) + (v || 0);
    }
    const fusedEntries = Object.entries(fused).sort((a,b) => (b[1]||0) - (a[1]||0));
    const maskedCats = fusedEntries.filter(([cat,_]) => cat !== "Montants").slice(0, 8);

    function qualityLabel() {
      // Headline amélioré avec compteurs détaillés
      const fields = sData.fields || {};
      const totalFields = Object.keys(fields).length;
      const extractedFields = Object.values(fields).filter(f => f?.value !== null && f?.value !== undefined).length;
      const suspiciousCount = (quality.suspicious_fields || []).length;
      const missingCritical = (quality.critical_missing_fields || []).length;
      
      // Déterminer le statut du bilan
      let balanceStatus = "";
      if (extractionDetails.doc_type === "bilan" || extractionDetails.routing_selected === "bilan") {
        const hasActif = fields.total_actif?.value != null;
        const hasPassif = fields.total_passif?.value != null;
        if (hasActif && hasPassif) {
          const actif = Number(fields.total_actif.value);
          const passif = Number(fields.total_passif.value);
          const gap = Math.abs(actif - passif);
          const tol = Math.max(500, passif * 0.03);
          if (gap <= tol) balanceStatus = "✓ Bilan équilibré";
          else balanceStatus = "⚠️ Bilan déséquilibré";
        } else {
          balanceStatus = "○ Bilan incomplet";
        }
      }
      
      // Construction du headline
      const parts = [];
      if (balanceStatus) parts.push(balanceStatus);
      parts.push(`${extractedFields}/${totalFields} champs extraits`);
      if (suspiciousCount > 0) parts.push(`${suspiciousCount} champ${suspiciousCount > 1 ? 's' : ''} à vérifier`);
      if (missingCritical > 0) parts.push(`${missingCritical} critique${missingCritical > 1 ? 's' : ''} manquant${missingCritical > 1 ? 's' : ''}`);
      
      const headline = parts.join(" · ");
      
      if (experienceHeadline) return experienceHeadline + "\n" + headline;
      if (!quality.needs_review) return headline + " · ✓ Prêt pour l'IA";
      if (qualityFlagsCount > 0) return headline;
      return headline + " · Revue manuelle recommandée";
    }

    const CRITICAL_FIELD_LABELS_FR = {
      total_actif: "Total actif",
      total_passif: "Total passif",
      capitaux_propres: "Capitaux propres",
      resultat_exercice: "Résultat de l'exercice",
      immobilisations: "Immobilisations",
      creances: "Créances",
      disponibilites: "Disponibilités",
      dettes_financieres: "Dettes financières",
      dettes_fournisseurs: "Dettes fournisseurs",
      chiffre_affaires: "Chiffre d'affaires",
      charges_externes: "Charges externes",
      resultat_exploitation: "Résultat d'exploitation",
      resultat_courant: "Résultat courant",
      resultat_net: "Résultat net",
      total_produits: "Total produits",
      total_charges: "Total charges",
      denomination_sci: "Dénomination SCI",
      date_cloture_exercice: "Date de clôture (exercice)",
      nombre_associes: "Nombre d'associés",
      revenus_bruts: "Revenus bruts",
      frais_charges_hors_interets: "Frais et charges hors intérêts",
      interets_emprunts: "Intérêts d'emprunts",
      revenu_net_foncier: "Revenu net foncier",
      societe: "Raison sociale",
      exercice: "Exercice",
      date_cloture: "Date de clôture",
    };
    function labelCriticalField(k) {
      return CRITICAL_FIELD_LABELS_FR[k] || String(k).replace(/_/g, " ");
    }

    // Mapping des sources en français lisible
    const SOURCE_LABELS = {
      "label:": "Lu directement",
      "fallback:": "Calculé/estimé",
      "derived:": "Déduit d'autres champs",
      "pcg_sum:": "Sommé depuis le plan comptable",
      "calculated:": "Calculé",
      "ocr_norm:": "OCR corrigé",
      "missing": "Non trouvé",
      "golden:": "Référence",
    };
    function translateSource(source) {
      if (!source) return "Source inconnue";
      for (const [prefix, label] of Object.entries(SOURCE_LABELS)) {
        if (source.startsWith(prefix)) return label;
      }
      return source;
    }

    // Badge de confiance pour un champ
    function confidenceBadge(confidence, source) {
      const n = Number(confidence || 0);
      let icon = "⚠️";
      let cls = "confidence-low";
      if (n >= 0.85) { icon = "✓"; cls = "confidence-high"; }
      else if (n >= 0.70) { icon = "~"; cls = "confidence-medium"; }
      const srcLabel = translateSource(source);
      return `<span class="confidence-badge ${cls}" title="Confiance: ${Math.round(n*100)}% | Source: ${srcLabel}">${icon} ${Math.round(n*100)}%</span>`;
    }

    // Formatage d'un montant
    function formatAmount(val) {
      if (val === null || val === undefined) return "—";
      if (typeof val === "number") {
        return val.toLocaleString("fr-FR", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
      }
      return String(val);
    }

    // Rendu des champs extraits avec badges
    function renderExtractedFields(fields) {
      if (!fields || Object.keys(fields).length === 0) return "<p>Aucun champ extrait</p>";

      const criticalFields = Object.keys(CRITICAL_FIELD_LABELS_FR);
      const sortEntries = (entries) => entries.sort((a, b) => {
        const aCrit = criticalFields.indexOf(a[0]);
        const bCrit = criticalFields.indexOf(b[0]);
        if (aCrit !== -1 && bCrit === -1) return -1;
        if (aCrit === -1 && bCrit !== -1) return 1;
        return a[0].localeCompare(b[0]);
      });

      const allEntries = Object.entries(fields);
      const foundEntries = sortEntries(allEntries.filter(([, f]) => (f?.confidence || 0) > 0));
      const missingEntries = sortEntries(allEntries.filter(([, f]) => (f?.confidence || 0) === 0));

      function makeRow([key, field], isMissing) {
        const label = labelCriticalField(key);
        const val = isMissing ? "—" : formatAmount(field?.value);
        const conf = field?.confidence || 0;
        const source = field?.source_hint || "";
        const isCalc = source && (source.startsWith("fallback:") || source.startsWith("derived:") || source.startsWith("calculated:"));
        const calcWarning = isCalc ? `<span class="calc-warning" title="Ce champ est calculé ou estimé — à vérifier">⚠️</span>` : "";
        const rowClass = isMissing ? "field-row field-missing" : (isCalc ? "field-row calculated" : "field-row");

        // Contextual note for specific missing/low-confidence fields
        const note = getFieldNote(key, source, conf);
        const noteHtml = note ? `<span class="field-note" title="${note}">ℹ️</span>` : "";

        return `<div class="${rowClass}">
          <span class="field-label">${label}${noteHtml}</span>
          <span class="field-value">${val} ${calcWarning}</span>
          <span class="field-confidence">${confidenceBadge(conf, source)}</span>
        </div>`;
      }

      const foundRows = foundEntries.map(e => makeRow(e, false)).join("");

      let missingSection = "";
      if (missingEntries.length > 0) {
        const missingRows = missingEntries.map(e => makeRow(e, true)).join("");
        missingSection = `
          <div class="missing-fields-section">
            <div class="missing-fields-toggle" onclick="this.parentElement.classList.toggle('open')">
              ▸ ${missingEntries.length} champ${missingEntries.length > 1 ? "s" : ""} non extrait${missingEntries.length > 1 ? "s" : ""}
            </div>
            <div class="missing-fields-body">
              ${missingRows}
            </div>
          </div>`;
      }

      return `<div class="extracted-fields-table">${foundRows}${missingSection}</div>`;
    }

    function getFieldNote(key, source, conf) {
      if (key === "raison_sociale") {
        return "La raison sociale est toujours anonymisée (remplacée par SOCIETE_X) — c'est normal.";
      }
      if (key === "disponibilites" && source && source.startsWith("calculated:")) {
        return "Disponibilités calculées par différence (total actif − immobilisations − créances). Valeur à 0 = bilan sans trésorerie distincte.";
      }
      if (key === "disponibilites" && conf === 0) {
        return "Disponibilités absentes du document ou confondues avec les créances — présence confirmée à 0.";
      }
      if (key === "exercice" && source && source.startsWith("derived:")) {
        return "Exercice déduit de la date de clôture (non lu directement dans l'en-tête).";
      }
      if (source && (source.startsWith("fallback:") || source.startsWith("calculated:"))) {
        return "Valeur estimée ou calculée — non lue directement dans le document.";
      }
      return null;
    }

    const FLAG_LABELS = {
      "emails_found": "Email potentiellement visible",
      "iban_found": "IBAN potentiellement visible",
      "siret_found": "SIRET potentiellement visible",
      "siren_found": "SIREN potentiellement visible",
      "uppercase_person_leftovers": "Nom/prénom potentiellement identifiable restant",
      "bilan_balance_mismatch": "Bilan : écart actif/passif au-delà de la tolérance",
      "bilan_balance_minor_gap": "Bilan : léger écart actif/passif (tolérance élargie)",
      "result_chain_inconsistent": "Compte de résultat : incohérence REX → RC → RN",
      "result_chain_minor_gap": "Compte de résultat : écart modéré sur la chaîne REX/RC/RN",
      "critical_fields_missing": "Champs critiques manquants pour ce type de document",
    };
    const FLAG_ACTIONS = {
      "uppercase_person_leftovers": "Vérifier les zones en majuscules restantes puis confirmer/masquer.",
      "emails_found": "Contrôler les emails restants et relancer l'extraction.",
      "iban_found": "Vérifier les IBAN visibles puis relancer l'anonymisation.",
      "siret_found": "Vérifier les identifiants entreprise non masqués.",
      "siren_found": "Vérifier les identifiants entreprise non masqués.",
      "bilan_balance_mismatch": "Contrôler les totaux actif/passif sur le document source ou relancer l'OCR.",
      "bilan_balance_minor_gap": "Vérifier rapidement les arrondis / synthèse plaquette ; souvent acceptable.",
      "result_chain_inconsistent": "Contrôler les trois résultats (exploitation, courant, net) sur le PDF source.",
      "result_chain_minor_gap": "Contrôler les postes financiers / exceptionnels entre les deux lignes concernées.",
      "critical_fields_missing": "Forcer le type de document ou vérifier la qualité du PDF.",
    };
    const rawFlags = Array.isArray(quality.quality_flags) ? quality.quality_flags : [];
    const suspiciousFields = Array.isArray(quality.suspicious_fields) ? quality.suspicious_fields : [];
    const reviewDetails = rawFlags.length
      ? rawFlags.map(f => `- ${FLAG_LABELS[f] || f}`).join("\n")
      : "- Aucun point de revue détecté";
    const criticalDetails = criticalMissing.length
      ? criticalMissing.map(f => `- ${labelCriticalField(f)} (${f})`).join("\n")
      : "- Aucun champ critique manquant";
    
    // suspicious_fields display
    const suspiciousDetails = suspiciousFields.length
      ? suspiciousFields.map(f => `- ${labelCriticalField(f)} (${f})`).join("\n")
      : "- Aucun champ suspect (tous les champs sont lus directement)";
    const suspiciousBadge = suspiciousFields.length
      ? `<span class="suspicious-badge">${suspiciousFields.length} champ${suspiciousFields.length > 1 ? 's' : ''} calculé${suspiciousFields.length > 1 ? 's' : ''}</span>`
      : `<span class="clean-badge">✓ Tous les champs sont lus directement</span>`;
    const recommendedAction = rawFlags.length
      ? (FLAG_ACTIONS[rawFlags[0]] || "Analyser les points listés puis relancer l'extraction.")
      : (criticalMissing.length
          ? "Les champs critiques n'ont pas été extraits: relancer avec type forcé et vérifier le document source."
          : "Aucune action immédiate requise.");
    const shownRoutingConfidence =
      extractionDetails.routing_confidence != null && criticalMissing.length > 0
        ? Math.min(extractionDetails.routing_confidence, 0.85)
        : extractionDetails.routing_confidence;

    const CAT_DESCR = {
      "Noms de personnes": "Les noms et identifiants de personnes ont été masqués.",
      "Email": "Les adresses email détectées ont été masquées.",
      "Téléphone": "Les numéros de téléphone ont été masqués.",
      "Identifiants bancaires": "Les identifiants et mentions bancaires détectés ont été masqués.",
      "Identifiants entreprise & fiscalité": "SIREN/SIRET et références fiscales masqués.",
      "Identifiant personnel": "Identifiants personnels masqués.",
      "Adresses et données de localisation": "Les adresses et éléments de localisation ont été masqués.",
      "Dates": "Dates détectées comme sensibles masquées/normalisées.",
      "Références documentaires": "Les références de facture et mentions associées ont été masquées.",
      "Valeurs sensibles (libellé : valeur)": "Paires libellé/valeur détectées comme sensibles masquées.",
      "Pays": "Pays masqués.",
      "Autre": "Autres champs détectés comme sensibles masqués.",
    };

    const maskedLines = maskedCats.length
      ? maskedCats.map(([cat,cnt]) => `- ${cat}: ${cnt}
  ${CAT_DESCR[cat] || "Masquage automatique d'une donnée sensible."}`).join("\n")
      : "- (aucune catégorie detectee)";

    maskedOut.innerHTML =
      `<div class="proof-cards3">
        <div class="proof-card masked">
          <div class="proof-card-title">Masqué</div>
          <div class="proof-card-value">${maskedTotal} éléments sensibles</div>
          <div class="proof-card-sub">Détail (principales catégories)</div>
          <div class="proof-card-sub" style="white-space:pre-wrap">${maskedLines}</div>
        </div>
        <div class="proof-card kept">
          <div class="proof-card-title">Conservé</div>
          <div class="proof-card-value">Montants & structure</div>
          <div class="proof-card-sub">${accountingCount != null ? `${accountingCount} lignes comptables extraites` : "Prêt pour l'exploitation comptable"}</div>
        </div>
        <div class="proof-card review">
          <div class="proof-card-title">À revoir ${suspiciousBadge}</div>
          <div class="proof-card-value">${quality.needs_review ? "Revue recommandée" : "Aucune revue requise"}</div>
          <div class="proof-card-sub">${qualityLabel()}</div>
          ${experienceSeg ? `<div class="proof-card-sub" style="opacity:0.92;font-size:0.9em">${experienceSeg}</div>` : ""}
          <div class="proof-card-sub" style="white-space:pre-wrap">${reviewDetails}</div>
          <div class="proof-card-sub" style="margin-top:6px;font-weight:700">Champs critiques manquants</div>
          <div class="proof-card-sub" style="white-space:pre-wrap">${criticalDetails}</div>
          <div class="proof-card-sub" style="margin-top:6px;font-weight:700;color:var(--amber)">Champs calculés / fallback</div>
          <div class="proof-card-sub" style="white-space:pre-wrap;font-size:0.9em">${suspiciousDetails}</div>
          <div class="proof-card-sub" style="margin-top:6px"><b>Action recommandée :</b> ${recommendedAction}</div>
          <div class="proof-card-sub">Étape conseillée : vérifier cette zone puis valider le document.</div>
        </div>
      </div>
      <div class="extract-details">
        <div class="extract-details-title">Détails d'extraction</div>
        <div class="extract-details-line">routing_requested: <b>${extractionDetails.routing_requested}</b></div>
        <div class="extract-details-line">routing_selected: <b>${extractionDetails.routing_selected}</b></div>
        <div class="extract-details-line">extractor_selected: <b>${extractionDetails.extractor_selected}</b></div>
        <div class="extract-details-line">doc_type final: <b>${extractionDetails.doc_type}</b></div>
        <div class="extract-details-line">routing_confidence: <b>${shownRoutingConfidence != null ? shownRoutingConfidence : "unknown"}</b></div>
        <div class="extract-details-line">découpe texte (smart split): <b>${
          extractionDetails.text_segmentation
            ? `${extractionDetails.text_segmentation.strategy} — ${extractionDetails.text_segmentation.segment_chars}/${extractionDetails.text_segmentation.full_chars} car. (score ${extractionDetails.text_segmentation.window_score ?? "—"})${extractionDetails.text_segmentation.fallback_to_full_text ? " → repli texte intégral (meilleure qualité)" : ""}`
            : "—"
        }</b></div>
      </div>
      <div class="extracted-fields-section">
        <div class="extracted-fields-title">📊 Champs extraits (${Object.keys(sData.fields || {}).length} champs)</div>
        <div class="extracted-fields-subtitle">✓ = confiance élevée | ~ = confiance moyenne | ⚠️ = calculé/à vérifier | ℹ️ = note contextuelle</div>
        ${renderExtractedFields(sData.fields)}
      </div>`;
  } catch (e) {
    // no-op
  }
}

function setAnonymizedPreview(docId, text) {
  lastAnonDocId = docId;
  lastAnonText = text || "";
  lastOriginalDocId = null;
  lastOriginalText = "";
  showPreview(lastAnonText);
  refreshMaskedSummary(docId);
  if (previewMode === "beforeafter" && lastOriginalDocId === docId && lastOriginalText) {
    showBeforeAfter(lastOriginalText, lastAnonText);
  }
  const modeLabel = $("profileSelect") ? $("profileSelect").value : "dataset_accounting_pseudo";
  $("statDetectionsSub").textContent = `mode appliqué: ${modeLabel}`;
  // Basculer automatiquement sur l'onglet Analyse pour afficher le résultat
  switchTab("analyse");
}

async function loadOriginalForBeforeAfter() {
  if (!lastAnonDocId || !lastAnonText) { toast("Chargez d'abord un document", "error"); return; }
  const docId = lastAnonDocId;
  if (!confirm("Afficher la version originale peut exposer des donnees sensibles. Continuer ?")) return;
  toast("Chargement version originale…", "info");
  try {
    const res = await fetch(
      `/api/v1/documents/${docId}/original?allow_original=true&max_chars=8000`,
      {headers:{Authorization:`Bearer ${accessToken}`}}
    );
    const raw = await res.text();
    if (!res.ok) {
      let detail = raw;
      try { detail = JSON.parse(raw).detail || raw; } catch {}
      toast(detail || "Erreur chargement original", "error");
      return;
    }
    lastOriginalDocId = docId;
    lastOriginalText = raw || "";
    showBeforeAfter(lastOriginalText, lastAnonText);
  } catch (e) {
    toast("Erreur reseau", "error");
  }
}
function setDetections(count, context) {
  $("statDetections").textContent = count;
  $("statDetectionsSub").textContent = context || "dernier document traité";
}
function showPlain(text) {
  previewOut.textContent = text || "";
}

function showProofSummary(data) {
  if (!data) { showPlain("Aucune preuve RGPD."); return; }
  const finalPresent = data.final_version_present ? "oui" : "non";
  const previewPresent = data.preview_version_present ? "oui" : "non";
  const maskedCount = data.detections_count || 0;
  showPlain(
    `Certificat de traitement — document ${data.document_id}

` +
    `Le document a été anonymisé avec succès.
` +
    `${maskedCount} éléments sensibles ont été masqués.
` +
    `Les informations utiles à l'exploitation comptable sont conservées (montants + structure).

` +
    `Prévisualisation générée: ${previewPresent}
` +
    `Version finale validée: ${finalPresent}

` +
    `Empreinte source (sha256): ${data.document_sha256}
` +
    `Empreinte preview (sha256): ${data.preview_version_sha256 || "(absente)"}
` +
    `Empreinte finale (sha256): ${data.final_version_sha256 || "(absente)"}

` +
    `Pour le détail des catégories et les zones à revoir, regarde le panneau « Ce qui a été masqué ».`
  );
}

function showAuditSummary(data) {
  if (!data) { showPlain("Aucun audit export."); return; }
  const types = data.detections_entity_types_count || {};
  const entries = Object.entries(types)
    .sort((a,b) => (b[1]||0) - (a[1]||0))
    .slice(0, 10);
  const topTypes = entries.length
    ? entries.map(([k,v]) => `${k}: ${v}`).join("\n")
    : "(aucun type)";

  const llmReqs = Array.isArray(data.llm_requests) ? data.llm_requests : [];
  const llmLine = llmReqs.length ? `LLM requêtes: ${llmReqs.length}` : "LLM requêtes: 0";

  showPlain(
    `AUDIT EXPORT (RGPD) — ${data.document_id}

` +
    `document_sha256: ${data.document_sha256}

` +
    `types entités (top):
${topTypes}

` +
    `${llmLine}
`
  );
}
function setDocDetection(docId, count) {
  docDetectionMap[docId] = count;
  const el = document.querySelector(`[data-doc-detection="${docId}"]`);
  if (el) el.textContent = `entités: ${count}`;
}

function refreshDocQaOptions() {
  const sel = $("docQaSelect");
  if (!sel) return;
  const prev = sel.value || lastActiveDocId || "";
  const docs = (currentDocs || []).filter(d => d.status === "ready");
  sel.innerHTML = '<option value="">Sélectionnez un document...</option>';
  docs.forEach((d) => {
    const q = docQualityMap[d.id] || {};
    const badge = q.ready_for_ai ? "Full" : (q.ready_for_ai_core ? "Core" : "Review");
    const opt = document.createElement("option");
    opt.value = d.id;
    opt.textContent = `${d.original_filename} (${badge})`;
    sel.appendChild(opt);
  });
  if (prev && docs.some(d => d.id === prev)) sel.value = prev;
}

function qualityBadgeFromQuality(q) {
  const quality = q || {};
  if (quality.ready_for_ai === true) {
    return {
      cls: "full-ready",
      label: "Full Ready",
      hint: "Extraction complète validée, prête pour export automatisé.",
    };
  }
  if (quality.ready_for_ai_core === true) {
    return {
      cls: "core-ready",
      label: "Core Ready",
      hint: "Données critiques validées ; enrichissement secondaire recommandé.",
    };
  }
  if (quality.needs_review === true) {
    return {
      cls: "review",
      label: "Review",
      hint: "Revue manuelle recommandée avant usage automatisé.",
    };
  }
  return {
    cls: "unknown",
    label: "Analyse",
    hint: "Qualité en cours d'évaluation.",
  };
}

function setDocQualityBadge(docId, quality) {
  docQualityMap[docId] = quality || null;
  const el = document.querySelector(`[data-doc-quality="${docId}"]`);
  if (!el) return;
  const badge = qualityBadgeFromQuality(quality || {});
  el.className = `doc-kpi doc-quality ${badge.cls}`;
  el.textContent = badge.label;
  el.title = badge.hint;
  const whyEl = document.querySelector(`[data-doc-why="${docId}"]`);
  if (whyEl) whyEl.textContent = qualityReasonText(quality || {});
  const actionEl = document.querySelector(`[data-doc-action="${docId}"]`);
  if (actionEl) {
    const doc = (currentDocs || []).find((d) => d.id === docId);
    actionEl.textContent = qualityActionText(doc || {}, quality || {});
  }
  const aiButtons = document.querySelectorAll(`[data-ai-btn-doc="${docId}"]`);
  const canUseAi = !!((quality || {}).ready_for_ai_core);
  aiButtons.forEach((btn) => {
    btn.disabled = !canUseAi;
    btn.classList.toggle("disabled", !canUseAi);
    btn.title = canUseAi
      ? "Action IA disponible"
      : "Action IA indisponible: ready_for_ai_core=false";
  });
  const aiHint = document.querySelector(`[data-ai-hint="${docId}"]`);
  if (aiHint) {
    aiHint.textContent = canUseAi
      ? (((quality || {}).ready_for_ai ? "IA enrichie disponible" : "IA disponible en mode prudent"))
      : "IA bloquée: document à revoir (ready_for_ai_core=false)";
  }
}

async function api(path, opts={}) {
  const headers = opts.headers || {};
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
  const res = await fetch(path, {...opts, headers});
  const raw = await res.text();
  let data;
  try { data = raw ? JSON.parse(raw) : {}; } catch { data = {raw}; }
  return {res, data};
}

/** Multipart upload : ne pas définir Content-Type (le navigateur pose le boundary). */
async function apiUploadMultipart(path, formData, onProgress) {
  const xhrUpload = () => new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", path, true);
    xhr.timeout = 300000; // 5 min pour Railway (OCR lourd)
    if (accessToken) xhr.setRequestHeader("Authorization", `Bearer ${accessToken}`);

    // Progression réelle pendant le transfert fichier (phase 1 : 0 → 55%)
    if (onProgress && xhr.upload) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          onProgress("transfer", Math.round((e.loaded / e.total) * 55));
        }
      };
      // Transfert terminé → serveur traite (phase 2 : 55% → attente)
      xhr.upload.onload = () => onProgress("processing", 60);
    }

    xhr.onload = () => {
      const raw = xhr.responseText || "";
      let data;
      try { data = raw ? JSON.parse(raw) : {}; } catch { data = { raw }; }
      resolve({
        res: {
          ok: xhr.status >= 200 && xhr.status < 300,
          status: xhr.status,
        },
        data,
      });
    };

    xhr.onerror = () => reject(new Error("network_error_upload"));
    xhr.ontimeout = () => reject(new Error("timeout_upload"));
    xhr.onabort = () => reject(new Error("aborted_upload"));
    xhr.send(formData);
  });

  const fetchUpload = async () => {
    const headers = {};
    if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
    const res = await fetch(path, { method: "POST", body: formData, headers });
    const raw = await res.text();
    let data;
    try { data = raw ? JSON.parse(raw) : {}; } catch { data = { raw }; }
    return { res, data };
  };

  // Fallback transport: certains navigateurs/environnements cassent XHR ou fetch selon le contexte.
  try {
    return await xhrUpload();
  } catch (firstErr) {
    const msg = String((firstErr && firstErr.message) || "").toLowerCase();
    const retriable =
      msg.includes("network_error_upload")
      || msg.includes("timeout_upload")
      || msg.includes("aborted_upload");
    if (!retriable) throw firstErr;
    return await fetchUpload();
  }
}

async function diagnoseUploadConnectivity() {
  // Best-effort network diagnosis to replace vague "transport failed" errors.
  try {
    const h = await fetch("/health", { method: "GET", cache: "no-store" });
    if (!h.ok) return { kind: "backend_unhealthy", status: h.status };
  } catch {
    return { kind: "backend_unreachable" };
  }

  if (!accessToken) return { kind: "missing_token" };

  try {
    const me = await fetch("/api/v1/users/me", {
      method: "GET",
      cache: "no-store",
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (me.status === 401 || me.status === 403) return { kind: "auth_expired", status: me.status };
    return { kind: "ok", status: me.status };
  } catch {
    return { kind: "auth_check_failed" };
  }
}

function formatApiDetail(data) {
  if (!data || data.detail == null) return "";
  const d = data.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    return d.map((x) => (x && x.msg) ? x.msg : JSON.stringify(x)).join("; ");
  }
  try {
    return JSON.stringify(d);
  } catch {
    return String(d);
  }
}

function formatSize(b) {
  if (b < 1024) return b + " B";
  if (b < 1048576) return (b/1024).toFixed(1) + " KB";
  return (b/1048576).toFixed(1) + " MB";
}

function docIcon(ext) {
  ext = (ext||"").toLowerCase();
  if (ext === "pdf") return {cls:"pdf",icon:"📕"};
  if (["png","jpg","jpeg","tiff"].includes(ext)) return {cls:"img",icon:"🖼️"};
  return {cls:"other",icon:"📄"};
}

function statusLabel(s) {
  const map = {uploaded:"reçu", processing:"en cours", ready:"prêt", failed:"erreur"};
  return map[s] || s || "inconnu";
}

function nextAction(doc) {
  const s = (doc && doc.status) || "";
  if (s === "uploaded") return "Prochaine action: lancer l'anonymisation.";
  if (s === "processing") return "Prochaine action: attendre la fin du traitement puis actualiser.";
  if (s === "ready") return "Prochaine action: vérifier Avant/Après, puis valider et exporter.";
  if (s === "failed") return "Prochaine action: réessayer avec un document plus lisible.";
  return "Prochaine action: ouvrir le document.";
}

function qualityReasonText(quality) {
  const q = quality || {};
  if (q.ready_for_ai === true) return "Document exploitable immédiatement.";
  if (q.ready_for_ai_core === true) return "Données clés exploitables, enrichissement secondaire recommandé.";
  if (Array.isArray(q.critical_missing_fields) && q.critical_missing_fields.length) {
    const miss = q.critical_missing_fields.slice(0, 2).join(", ");
    return `Champs critiques manquants: ${miss}${q.critical_missing_fields.length > 2 ? "…" : ""}.`;
  }
  if (q.needs_review === true) return "Revue humaine recommandée avant usage.";
  return "Analyse qualité en cours.";
}

function qualityActionText(doc, quality) {
  const s = (doc && doc.status) || "";
  const q = quality || {};
  if (s === "uploaded") return "Action: lancer le traitement.";
  if (s === "processing") return "Action: attendre puis actualiser.";
  if (s === "failed") return "Action: réuploader une version plus lisible.";
  if (q.ready_for_ai === true) return "Action: exporter le rapport PDF et partager.";
  if (q.ready_for_ai_core === true) return "Action: exporter le rapport puis vérifier les points secondaires.";
  if (Array.isArray(q.critical_missing_fields) && q.critical_missing_fields.length) return "Action: corriger/revalider avant export final.";
  return "Action: valider puis exporter un rapport lisible.";
}

function renderDocs(items) {
  currentDocs = items || [];
  const total = currentDocs.length;
  const ready = currentDocs.filter(d=>d.status==="ready").length;
  const processing = currentDocs.filter(d=>d.status==="processing").length;
  $("statTotal").textContent = total;
  $("statReady").textContent = ready;
  $("statProcessing").textContent = processing;

  if (!currentDocs.length) {
    docList.innerHTML = '<div class="docs-empty"><div class="empty-icon">📂</div><p>Aucun document.<br>Uploadez votre premier fichier.</p></div>';
    return;
  }
  docList.innerHTML = "";
  // Group by client name (first tag)
  const groups = new Map();
  currentDocs.forEach(doc => {
    const client = (Array.isArray(doc.tags) && doc.tags.length && doc.tags[0]) ? doc.tags[0] : "";
    if (!groups.has(client)) groups.set(client, []);
    groups.get(client).push(doc);
  });
  // Sort: named clients first (alpha), then unnamed
  const sortedKeys = Array.from(groups.keys()).sort((a, b) => {
    if (!a && b) return 1;
    if (a && !b) return -1;
    return a.localeCompare(b, "fr");
  });
  let globalIdx = 0;
  sortedKeys.forEach(clientKey => {
    const groupDocs = groups.get(clientKey);
    if (clientKey) {
      const header = document.createElement("div");
      header.className = "doc-client-group";
      header.innerHTML = `<span class="doc-client-icon">👤</span><span class="doc-client-name">${clientKey}</span><span class="doc-client-count">${groupDocs.length} doc${groupDocs.length > 1 ? "s" : ""}</span>`;
      docList.appendChild(header);
    }
    groupDocs.forEach((doc) => {
      const i = globalIdx++;
      const ic = docIcon(doc.extension);
      const el = document.createElement("div");
      el.className = "doc-item";
      el.style.animationDelay = `${i*0.05}s`;
    el.innerHTML = `
      <div class="doc-icon ${ic.cls}">${ic.icon}</div>
      <div class="doc-info">
        <div class="doc-head">
          <div class="doc-name" title="${doc.original_filename}">${doc.original_filename}</div>
          <span class="doc-status ${doc.status}">${statusLabel(doc.status)}</span>
        </div>
        <div class="doc-meta"><span>${formatSize(doc.size_bytes)}</span></div>
        <div class="doc-kpis">
          <span class="doc-kpi expert-only" data-doc-detection="${doc.id}">${docDetectionMap[doc.id] != null ? `entités: ${docDetectionMap[doc.id]}` : "entités: —"}</span>
          <span class="doc-kpi doc-quality unknown" data-doc-quality="${doc.id}">Analyse</span>
        </div>
        <div class="doc-why" data-doc-why="${doc.id}">${qualityReasonText(docQualityMap[doc.id])}</div>
        <div class="doc-next" data-doc-action="${doc.id}">${qualityActionText(doc, docQualityMap[doc.id])}</div>
        <div class="doc-actions ai-actions">
          <span class="doc-actions-title">Actions IA</span>
          <button class="btn-act" data-a="aisummary" data-id="${doc.id}" data-ai-btn-doc="${doc.id}">✨ Résumer</button>
          <button class="btn-act" data-a="aireview" data-id="${doc.id}" data-ai-btn-doc="${doc.id}">🔎 Points à vérifier</button>
          <button class="btn-act" data-a="aidraft" data-id="${doc.id}" data-ai-btn-doc="${doc.id}">📝 Rédiger une note</button>
          <button class="btn-act" data-a="askdoc" data-id="${doc.id}" data-ai-btn-doc="${doc.id}">💬 Poser une question</button>
          <span class="doc-ai-hint" data-ai-hint="${doc.id}">Vérification qualité en cours…</span>
        </div>
        <div class="doc-actions core-actions">
          <span class="doc-actions-title">Actions document</span>
          <button class="btn-act success" data-a="processall" data-id="${doc.id}">🚀 Traiter</button>
          <button class="btn-act success" data-a="validate" data-id="${doc.id}">✓ Valider</button>
          <button class="btn-act primary" data-a="exportreportpdf" data-id="${doc.id}">📄 Exporter PDF</button>
          <button class="btn-act" data-a="exportreportdoc" data-id="${doc.id}">📝 Exporter DOC</button>
          <details class="expert-only">
            <summary class="btn-act" style="display:inline-flex;list-style:none">Plus</summary>
            <div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:6px">
              <button class="btn-act" data-a="rerunextract" data-id="${doc.id}">🔁 Relancer l'extraction</button>
              <button class="btn-act" data-a="anonymize" data-id="${doc.id}">🔒 Anonymiser</button>
              <button class="btn-act" data-a="preview" data-id="${doc.id}">👁️ Prévisualiser</button>
              <button class="btn-act" data-a="exportstructured" data-id="${doc.id}">📤 Exporter structuré</button>
              <button class="btn-act" data-a="exportdataset" data-id="${doc.id}">📊 Exporter dataset</button>
              <button class="btn-act" data-a="aisummary" data-id="${doc.id}">🤖 Synthèse IA</button>
              <button class="btn-act" data-a="proof" data-id="${doc.id}">🛡️ Preuve</button>
              <button class="btn-act" data-a="auditexport" data-id="${doc.id}">🧾 Audit</button>
            </div>
          </details>
          <button class="btn-act danger" data-a="delete" data-id="${doc.id}">🗑️</button>
        </div>
      </div>`;
      docList.appendChild(el);
      setDocQualityBadge(doc.id, docQualityMap[doc.id]);
    });
  });
  refreshDocQaOptions();
  // Appliquer les filtres de recherche après le rendu
  applyDocFilter();
  // Mettre à jour l'onglet Exports si actif
  const exportsTab = $("tab-exports");
  if (exportsTab && exportsTab.classList.contains("active")) renderExportsList();
}

async function refreshStatusSummary() {
  if (!accessToken) return;
  const fullEl = $("sumFullReady");
  const coreEl = $("sumCoreReady");
  const reviewEl = $("sumReview");
  const avgEl = $("sumAvgReady");
  const flagsEl = $("sumTopFlags");
  if (!fullEl || !coreEl || !reviewEl || !avgEl || !flagsEl) return;
  try {
    const days = Number(statusSummaryDays || 30);
    const qs = `days=${encodeURIComponent(String(days))}&doc_type=auto&max_docs_for_quality=30`;
    const { res, data } = await api(`/api/v1/documents/status-summary?${qs}`);
    if (!res.ok) return;
    const q = data && data.quality_distribution ? data.quality_distribution : {};
    fullEl.textContent = String(q.full_ready || 0);
    coreEl.textContent = String(q.core_ready || 0);
    reviewEl.textContent = String(q.review || 0);
    const avg = data && data.avg_ready_latency_seconds;
    avgEl.textContent = (typeof avg === "number") ? `${avg.toFixed(1)}s` : "—";
    const top = Array.isArray(data && data.top_quality_flags) ? data.top_quality_flags : [];
    flagsEl.textContent = top.length ? `${top[0].flag} (${top[0].count})` : "—";
  } catch {}
}

function updateStatusRangeButtons() {
  const row = $("statusRangeRow");
  if (!row) return;
  row.querySelectorAll(".status-range-btn").forEach((btn) => {
    const days = Number(btn.dataset.days || 0);
    btn.classList.toggle("active", days === Number(statusSummaryDays));
  });
}

function bindStatusRangeControls() {
  const row = $("statusRangeRow");
  if (!row || row.dataset.bound === "1") return;
  row.dataset.bound = "1";
  row.addEventListener("click", async (e) => {
    const btn = e.target.closest(".status-range-btn");
    if (!btn) return;
    const next = Number(btn.dataset.days || 0);
    if (![7, 30, 90].includes(next)) return;
    if (next === Number(statusSummaryDays)) return;
    statusSummaryDays = next;
    updateStatusRangeButtons();
    await refreshStatusSummary();
  });
  updateStatusRangeButtons();
}

async function refreshDocs() {
  if (!accessToken) return;
  try {
    const {res, data} = await api("/api/v1/documents");
    showApi(data);
    if (res.ok) {
      renderDocs(data);
      await refreshDocDetections(data);
      await refreshStatusSummary();
    }
  } catch(e) { toast("Erreur réseau", "error"); }
}

async function refreshDocDetections(items) {
  const docs = (items || []).filter(d => d.status === "ready");
  for (const doc of docs) {
    try {
      const {res, data} = await api(`/api/v1/documents/${doc.id}/preview`);
      if (res.ok) setDocDetection(doc.id, data.detections_count || 0);
    } catch {}
    try {
      const { res, data } = await api(`/api/v1/documents/${doc.id}/dataset-summary`);
      if (res.ok) {
        const q = (data && data.quality) ? data.quality : {};
        setDocQualityBadge(doc.id, q);
      } else {
        setDocQualityBadge(doc.id, null);
      }
    } catch {
      setDocQualityBadge(doc.id, null);
    }
  }
  refreshDocQaOptions();
}

async function loadDocQualitySnapshot(docId) {
  const { res, data } = await api(`/api/v1/documents/${docId}/dataset-summary`);
  if (!res.ok) throw new Error((data && data.detail) ? String(data.detail) : "Impossible de lire la qualité");
  return (data && data.quality) ? data.quality : {};
}

function renderDocQaAnswer(question, data, quality) {
  let parsed = {};
  try { parsed = JSON.parse(data.summary_json_text || "{}"); } catch {}
  const q = quality || {};
  const points = Array.isArray(parsed.points_cles) ? parsed.points_cles : [];
  const alerts = Array.isArray(parsed.anomalies_ou_alertes) ? parsed.anomalies_ou_alertes : [];
  const follow = Array.isArray(parsed.questions_de_revue) ? parsed.questions_de_revue : [];
  previewOut.innerHTML = `
    <div class="ai-summary">
      <div class="ai-head">
        <div class="ai-tools"><div class="ai-mode ok">Q&A document</div></div>
        <div class="ai-confidence">Mode: <b>${q.ready_for_ai ? "riche" : "prudent"}</b></div>
      </div>
      <div class="ai-status">Question: <b>${escapeHtml(question)}</b></div>
      <div class="ai-security">Réponse cadrée par les facts backend (ConfiDoc source de vérité).</div>
      <div class="ai-block"><div class="ai-title">Réponse</div><div>${escapeHtml(parsed.resume_executif || "Aucune réponse disponible.")}</div></div>
      <div class="ai-block"><div class="ai-title">Points clés</div><ul class="ai-list">${points.map(x => `<li>${escapeHtml(x)}</li>`).join("")}</ul></div>
      <div class="ai-block"><div class="ai-title">Points à vérifier</div><ul class="ai-list">${alerts.map(x => `<li>${escapeHtml(x)}</li>`).join("")}</ul></div>
      <div class="ai-block"><div class="ai-title">Questions de revue</div><ul class="ai-list">${follow.map(x => `<li>${escapeHtml(x)}</li>`).join("")}</ul></div>
    </div>`;
  switchTab("analyse");
}

async function askDocumentQuestion() {
  const qInput = $("docQaQuestion");
  const docSel = $("docQaSelect");
  const askBtn = $("askDocBtn");
  if (!qInput || !docSel || !askBtn) return;
  if (!accessToken) { toast("Connectez-vous d'abord", "error"); return; }
  const docId = (docSel.value || "").trim();
  const question = (qInput.value || "").trim();
  if (!docId) { toast("Sélectionnez un document", "error"); return; }
  if (!question) { toast("Saisissez une question", "error"); return; }

  setActionBusy(askBtn, true, "Question...");
  try {
    const quality = await loadDocQualitySnapshot(docId);
    if (!quality.ready_for_ai_core) {
      previewOut.innerHTML = `
        <div class="ai-summary">
          <div class="ai-head"><div class="ai-tools"><div class="ai-mode fallback">Q&A limité</div></div></div>
          <div class="ai-status">Document non prêt pour Q&A (<b>ready_for_ai_core=false</b>).</div>
          <div class="ai-block"><div class="ai-title">Points bloquants</div><div>${escapeHtml((quality.quality_flags || []).join(", ") || "Aucun détail disponible.")}</div></div>
        </div>`;
      toast("Q&A bloqué: document à revoir", "error");
      return;
    }
    const requestedDocType = currentDocTypeRequested();
    const path = `/api/v1/ai/summary/${docId}?doc_type=${encodeURIComponent(requestedDocType)}&llm_provider=auto&kimi_mode=question&question=${encodeURIComponent(question)}`;
    const { res, data } = await api(path, { method: "POST" });
    showApi(data);
    if (!res.ok) {
      toast((data && data.detail) ? String(data.detail) : "Q&A échoué", "error");
      return;
    }
    renderDocQaAnswer(question, data, quality);
    toast(quality.ready_for_ai ? "Réponse Q&A prête" : "Réponse Q&A (mode prudent)", "success");
  } catch (e) {
    toast((e && e.message) ? e.message : "Erreur réseau Q&A", "error");
  } finally {
    setActionBusy(askBtn, false);
  }
}

async function runAiDocAction(docId, kimiMode) {
  // Use fresh quality from API, but also check cached version for consistency warning
  const freshQuality = await loadDocQualitySnapshot(docId);
  const cachedQuality = docQualityMap[docId] || {};
  
  // Debug: log if inconsistent
  if (cachedQuality.ready_for_ai && !freshQuality.ready_for_ai_core) {
    console.warn("Quality inconsistency detected:", {
      cached: cachedQuality,
      fresh: freshQuality
    });
  }
  
  const quality = freshQuality; // Always use fresh for decision
  
  if (!quality.ready_for_ai_core) {
    previewOut.innerHTML = `
      <div class="ai-summary">
        <div class="ai-head"><div class="ai-tools"><div class="ai-mode fallback">Action IA limitée</div></div></div>
        <div class="ai-status">Document non prêt pour analyse assistée (<b>ready_for_ai_core=false</b>).</div>
        <div class="ai-block"><div class="ai-title">Points bloquants</div><div>${escapeHtml((quality.quality_flags || []).join(", ") || "Aucun détail disponible.")}</div></div>
        <div class="ai-block" style="font-size:12px;color:var(--text-dim);margin-top:8px">
          Le document a peut-être changé de statut. Rafraîchissez la page.
        </div>
      </div>`;
    toast("Action IA bloquée: document à revoir", "error");
    // Refresh the badge to show correct status
    setDocQualityBadge(docId, quality);
    return;
  }
  const requestedDocType = currentDocTypeRequested();
  const path = `/api/v1/ai/summary/${docId}?doc_type=${encodeURIComponent(requestedDocType)}&llm_provider=auto&kimi_mode=${encodeURIComponent(kimiMode)}`;
  const { res, data } = await api(path, { method: "POST" });
  showApi(data);
  if (!res.ok) {
    toast((data && data.detail) ? String(data.detail) : "Action IA échouée", "error");
    return;
  }
  let parsed = null;
  try { parsed = JSON.parse(data.summary_json_text || "{}"); } catch {}
  showAiSummaryCard({ ...data, summary: parsed || {} });
  const modeLabel = kimiMode === "summary" ? "Résumé"
    : kimiMode === "review" ? "Points à vérifier"
    : "Rédaction";
  toast(quality.ready_for_ai ? `${modeLabel} prêt` : `${modeLabel} prêt (mode prudent)`, "success");
}

// Preview mode (anonymisé / avant-apres)
const modeAnonBtn = $("modeAnonOnly");
const modeBeforeAfterBtn = $("modeBeforeAfter");
if (modeAnonBtn) {
  modeAnonBtn.addEventListener("click", () => {
    setPreviewMode("anon");
    if (lastAnonText) showPreview(lastAnonText);
  });
}
if (modeBeforeAfterBtn) {
  modeBeforeAfterBtn.addEventListener("click", async () => {
    setPreviewMode("beforeafter");
    await loadOriginalForBeforeAfter();
  });
}

// Login
$("loginBtn").addEventListener("click", async () => {
  const btn = $("loginBtn");
  const email = $("email").value.trim();
  const pw = $("password").value;
  if (!email || !pw) { toast("Remplissez tous les champs", "error"); return; }
  btn.disabled = true;
  btn.innerHTML = '<div class="spinner"></div>';
  try {
    const {res, data} = await api("/api/v1/auth/login", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({email, password: pw})
    });
    showApi(data);
    if (!res.ok) {
      const detail = (data && data.detail) || (data && data.raw) || `Échec login (${res.status})`;
      toast(detail, "error");
      return;
    }
    accessToken = data.access_token || "";
    $("userEmail").textContent = email.split("@")[0];
    $("userAvatar").textContent = email[0].toUpperCase();
    $("loginScreen").classList.remove("active");
    $("dashScreen").classList.add("active");
    toast("Connecté avec succès", "success");
    await refreshDocs();
  } catch(e) { toast("Erreur réseau", "error"); }
  finally { btn.disabled = false; btn.innerHTML = '<span class="btn-text">Se connecter</span>'; }
});

// Enter key login
$("password").addEventListener("keydown", e => { if (e.key === "Enter") $("loginBtn").click(); });
$("email").addEventListener("keydown", e => { if (e.key === "Enter") $("password").focus(); });

// Logout
$("logoutBtn").addEventListener("click", async () => {
  try { await api("/api/v1/auth/logout", {method:"POST"}); } catch {}
  accessToken = "";
  $("dashScreen").classList.remove("active");
  $("loginScreen").classList.add("active");
  toast("Déconnecté", "info");
});

// Upload drag & drop (ne pas assigner fileInput.files : interdit / instable dans les navigateurs)
const dropZone = $("dropZone");
const fileInput = $("fileInput");
["dragenter", "dragover"].forEach((ev) =>
  dropZone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropZone.classList.add("dragover");
  })
);
["dragleave"].forEach((ev) =>
  dropZone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
  })
);
dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("dragover");
  if (e.dataTransfer.files && e.dataTransfer.files.length) {
    doUploadFile(e.dataTransfer.files[0]);
  }
});
fileInput.addEventListener("change", () => {
  if (fileInput.files && fileInput.files.length) doUploadFile(fileInput.files[0]);
});

async function doUploadFile(file) {
  if (!accessToken) { toast("Connectez-vous d'abord", "error"); return; }
  if (!file) return;
  const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;
  if (file.size > MAX_UPLOAD_BYTES) {
    toast(`Fichier trop volumineux (${Math.round(file.size / (1024 * 1024))} MB). Maximum: 50 MB.`, "error");
    return;
  }
  // Vérifie que le fichier est réellement lisible localement (iCloud/Drive placeholders).
  try {
    await file.slice(0, Math.min(file.size, 64 * 1024)).arrayBuffer();
  } catch {
    toast("Fichier non lisible localement. Ouvre-le d'abord pour forcer son téléchargement puis réessaie.", "error");
    return;
  }
  const prog = $("uploadProgress");
  const fill = $("progressFill");
  const progText = $("progText");
  prog.classList.add("active");
  fill.style.width = "30%";
  progText.textContent = `Upload de ${file.name}…`;

  const form = new FormData();
  form.append("file", file, file.name);
  const profile = $("profileSelect").value;
  const requestedDocType = currentDocTypeRequested();
  const autoRequested = $("autoAnonymize").checked;
  // Sur des PDFs lourds, l'auto traitement inline peut dépasser le timeout HTTP
  // (surtout en prod) et provoquer un "Load failed" côté navigateur.
  const AUTO_SAFE_MAX_BYTES = 2 * 1024 * 1024;
  const auto = autoRequested && file.size <= AUTO_SAFE_MAX_BYTES;
  if (autoRequested && !auto) {
    toast("Fichier volumineux: upload rapide sans auto-traitement. Clique ensuite sur « Traiter ».", "info");
  }
  const clientName = ($("clientNameInput") || {}).value || "";
  const uploadUrl = `/api/v1/uploads?auto_anonymize=${auto}&profile=${encodeURIComponent(profile)}&document_type=${encodeURIComponent(requestedDocType)}&client_name=${encodeURIComponent(clientName.trim())}`;

  // Animation lente 60% → 90% pendant le traitement serveur (OCR / anonymisation)
  let processingInterval = null;
  let currentFakePct = 60;
  function startProcessingAnimation() {
    fill.classList.add("pulsing");
    processingInterval = setInterval(() => {
      if (currentFakePct < 90) {
        currentFakePct += 0.5;
        fill.style.width = currentFakePct + "%";
      }
    }, 600);
  }
  function stopProcessingAnimation() {
    if (processingInterval) { clearInterval(processingInterval); processingInterval = null; }
    fill.classList.remove("pulsing");
  }

  function onUploadProgress(phase, pct) {
    if (phase === "transfer") {
      fill.style.width = pct + "%";
      progText.textContent = `Envoi… ${pct}%`;
    } else if (phase === "processing") {
      fill.style.width = "60%";
      currentFakePct = 60;
      progText.textContent = auto ? "Traitement en cours (OCR + anonymisation)…" : "Finalisation…";
      startProcessingAnimation();
    }
  }

  try {
    setStage("upload", "Upload du document en cours...");
    fill.style.width = "5%";
    progText.textContent = `Envoi de ${file.name}…`;
    const { res, data } = await apiUploadMultipart(uploadUrl, form, onUploadProgress);
    stopProcessingAnimation();
    showApi(data);
    if (!res.ok) {
      const msg = formatApiDetail(data) || res.status;
      toast(`Upload échoué: ${msg}`, "error");
      fill.style.width = "100%"; fill.style.background = "var(--rose)";
      progText.textContent = "Échec";
      setStage("upload", "Échec pendant l'upload.");
    } else {
      fill.style.width = "100%";
      progText.textContent = "Terminé !";
      if (auto) {
        setStage("extract", "Document reçu. OCR/anonymisation/extraction terminés.");
      } else {
        setStage("upload", "Upload terminé. Lancez l'anonymisation.");
      }
      const count = data && data.processing ? data.processing.detections_count : null;
      toast(`${file.name} uploadé — ${count != null ? count + " détections" : "prêt"}`, "success");
      await refreshDocs();
    }
  } catch (e) {
    stopProcessingAnimation();
    const errMsg = e && e.message ? e.message : String(e);
    const lower = String(errMsg).toLowerCase();
    if (
      lower.includes("load failed")
      || lower.includes("failed to fetch")
      || lower.includes("networkerror")
      || lower.includes("network_error_upload")
      || lower.includes("aborted_upload")
    ) {
      const diag = await diagnoseUploadConnectivity();
      if (diag.kind === "backend_unreachable") {
        toast("Backend injoignable depuis le navigateur. Vérifie la connexion puis réessaie.", "error");
      } else if (diag.kind === "backend_unhealthy") {
        toast(`Backend indisponible (health ${diag.status}). Réessaie dans 30 secondes.`, "error");
      } else if (diag.kind === "auth_expired" || diag.kind === "missing_token") {
        toast("Session expirée. Déconnecte-toi/reconnecte-toi puis réessaie l'upload.", "error");
      } else {
        toast("Échec de transport navigateur pendant l'upload. Réessaie, puis recharge la page.", "error");
      }
    } else if (lower.includes("timeout_upload")) {
      toast("Upload trop long (timeout 120s). Réessaie avec un fichier plus léger.", "error");
    } else {
      toast(`Erreur réseau: ${errMsg}`, "error");
    }
  } finally {
    setTimeout(() => {
      prog.classList.remove("active");
      fill.style.width = "0";
      fill.style.background = "";
    }, 2500);
    fileInput.value = "";
  }
}

// Refresh
$("refreshBtn").addEventListener("click", () => { refreshDocs(); toast("Liste actualisée", "info"); });
bindStatusRangeControls();

const purgeAllBtn = $("purgeAllDocsBtn");
if (purgeAllBtn) {
  purgeAllBtn.addEventListener("click", () => openPurgeModal());
}

function applyExpertMode(enabled) {
  document.querySelectorAll(".expert-only").forEach(el => {
    el.classList.toggle("show", !!enabled);
  });
}
const expertToggle = $("expertModeToggle");
if (expertToggle) {
  expertToggle.addEventListener("change", (e) => {
    const on = !!(e && e.target && e.target.checked);
    applyExpertMode(on);
    toast(on ? "Mode expert activé" : "Mode expert désactivé", "info");
  });
}
applyExpertMode(false);

// KB ask
async function askKb() {
  const input = $("kbQuestion");
  const query = (input.value || "").trim();
  if (!accessToken) { toast("Connectez-vous d'abord", "error"); return; }
  if (!query) { toast("Saisissez une question", "error"); return; }

  const askBtn = $("askKbBtn");
  askBtn.disabled = true;
  try {
    // Ingestion automatique des documents "ready" avant recherche KB
    const readyDocs = (currentDocs || []).filter(d => d.status === "ready");
    if (readyDocs.length) {
      toast("Indexation KB en cours…", "info");
      for (const doc of readyDocs) {
        const {res: ingestRes} = await api(`/api/v1/kb/ingest/${doc.id}`, {method: "POST"});
        if (!ingestRes.ok && ingestRes.status !== 404) {
          // On continue sur les autres docs: un doc invalide ne doit pas bloquer les questions
        }
      }
    }

    toast("Recherche dans la base anonyme…", "info");
    $("statDetectionsSub").textContent = "compteur d'anonymisation, pas des questions";
    const {res, data} = await api("/api/v1/kb/search", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({query, limit: 20, include_needs_review: true}),
    });
    showApi(data);
    if (!res.ok) { toast(data.detail || "Recherche KB échouée", "error"); return; }

    const results = Array.isArray(data.results) ? data.results : [];
    if (!results.length) {
      showPreview("Aucun résultat dans la base anonyme pour cette question.");
      toast("Aucun résultat", "info");
      return;
    }

    const lines = results.slice(0, 8).map((r, idx) => {
      if (r.type === "accounting_record") {
        return `${idx + 1}. [record] ${r.code_comptable || "-"} | ${r.categorie_pcg || "-"} | ${r.montant_raw || "-"}
${r.libelle || ""}`;
      }
      return `${idx + 1}. [chunk] ${r.chunk_text || ""}`;
    });
    showPreview(`Question: ${query}

Résultats (${results.length}):

${lines.join("\n\n")}`);
    toast(`${results.length} résultat(s) trouvés`, "success");
  } catch (e) {
    toast("Erreur réseau", "error");
  } finally {
    askBtn.disabled = false;
  }
}

$("askKbBtn").addEventListener("click", askKb);
$("kbQuestion").addEventListener("keydown", e => { if (e.key === "Enter") askKb(); });
const askDocBtn = $("askDocBtn");
if (askDocBtn) askDocBtn.addEventListener("click", askDocumentQuestion);
const docQaQuestion = $("docQaQuestion");
if (docQaQuestion) docQaQuestion.addEventListener("keydown", e => { if (e.key === "Enter") askDocumentQuestion(); });
document.querySelectorAll("[data-qa-suggest]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const txt = btn.getAttribute("data-qa-suggest") || "";
    if ($("docQaQuestion")) $("docQaQuestion").value = txt;
    if ($("docQaQuestion")) $("docQaQuestion").focus();
  });
});

// Document actions
docList.addEventListener("click", async e => {
  const btn = e.target.closest("[data-a]");
  if (!btn || !accessToken) return;
  const action = btn.dataset.a;
  const id = btn.dataset.id;
    lastActiveDocId = id || lastActiveDocId;
    if ($("docQaSelect") && id) $("docQaSelect").value = id;
    updateActiveDocBanner();
  const profile = $("profileSelect").value;
  const requestedDocType = currentDocTypeRequested();
  const busyLabelByAction = {
    processall: "Traitement...",
    anonymize: "Anonymisation...",
    rerunextract: "Relance...",
    preview: "Chargement...",
    validate: "Validation...",
    exportstructured: "Export...",
    exportreportdoc: "Export...",
    exportreportpdf: "Export...",
    exportdataset: "Export...",
    aisummary: "Synthèse...",
    aisummary: "Résumé...",
    aireview: "Revue...",
    aidraft: "Rédaction...",
    proof: "Preuve...",
    auditexport: "Audit...",
    delete: "Suppression...",
  };
  setActionBusy(btn, true, busyLabelByAction[action] || "Traitement...");
  try {
    toast(`Action en cours: ${action}`, "info");
    if (action === "processall") {
      setStage("anonymize", "Anonymisation en cours...");
      toast("Traitement complet en cours…", "info");
      const a1 = await api(`/api/v1/documents/${id}/anonymize?profile=${encodeURIComponent(profile)}&document_type=${encodeURIComponent(requestedDocType)}`, {method:"POST"});
      showApi(a1.data);
      if (!a1.res.ok) { toast(a1.data.detail||"Échec anonymisation", "error"); return; }
      setDetections(a1.data.detections_count||0, "dernier document traité");
      setDocDetection(id, a1.data.detections_count||0);

      const a2 = await api(`/api/v1/documents/${id}/preview`);
      showApi(a2.data);
      if (!a2.res.ok) { toast(a2.data.detail||"Échec preview", "error"); return; }
      setAnonymizedPreview(id, a2.data.preview_text||"");

      const a3 = await api(`/api/v1/documents/${id}/validate`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          doc_type: requestedDocType === "auto" ? "generic" : requestedDocType,
          profile_used: profile,
          feedbacks: [],
        }),
      });
      showApi(a3.data);
      if (!a3.res.ok) { toast(a3.data.detail||"Échec validation", "error"); return; }

      const a4 = await fetch(`/api/v1/documents/${id}/export-dataset`, {headers:{Authorization:`Bearer ${accessToken}`}});
      const a4data = await a4.json().catch(()=>({}));
      showApi(a4data);
      if (!a4.ok) { toast("Échec export dataset", "error"); return; }
      showPreview(a4data.anonymized_text||"Dataset exporté");
      setStage("ready", "Document prêt : validation et export terminés.");
      const q4 = a4data && a4data.quality ? a4data.quality : {};
      toast(`Traitement terminé : ${q4.detections_count||0} entités. Revue requise : ${q4.needs_review ? "oui" : "non"}.`, "success");
    } else if (action === "anonymize") {
      setStage("anonymize", "Anonymisation en cours...");
      toast("Anonymisation en cours…", "info");
      const {res, data} = await api(`/api/v1/documents/${id}/anonymize?profile=${encodeURIComponent(profile)}&document_type=${encodeURIComponent(requestedDocType)}`, {method:"POST"});
      showApi(data);
      if (res.ok) { setAnonymizedPreview(id, data.preview_text||""); toast(`${data.detections_count||0} entités détectées`, "success"); setDetections(data.detections_count||0, "dernier document traité"); setDocDetection(id, data.detections_count||0); setStage("extract", "Anonymisation terminée. Données extraites."); }
      else toast(data.detail||"Échec", "error");
    } else if (action === "rerunextract") {
      setStage("extract", `Relance extraction (${requestedDocType}) en cours...`);
      toast(`Relance extraction (${requestedDocType})…`, "info");
      // Utilise l'endpoint structuré (plus léger et plus stable) au lieu de renvoyer tout le preview anonymisé.
      const {res, data} = await api(`/api/v1/documents/${id}/export-structured-dataset?doc_type=${encodeURIComponent(requestedDocType)}`);
      showApi(data);
      if (!res.ok) {
        toast(data.detail || "Relance extraction échouée", "error");
        return;
      }
      const q = (data && data.quality) ? data.quality : {};
      setDocQualityBadge(id, q);
      const badge = qualityBadgeFromQuality(q);
      toast(`Extraction relancée (${requestedDocType}) • ${badge.label}`, "success");
      setStage("extract", `Extraction relancée (${requestedDocType}) terminée.`);
      await refreshMaskedSummary(id);
    } else if (action === "preview") {
      const {res, data} = await api(`/api/v1/documents/${id}/preview`);
      showApi(data);
      if (res.ok) setAnonymizedPreview(id, data.preview_text||""); else toast(data.detail||"Pas de preview", "error");
    } else if (action === "validate") {
      const reqDt = currentDocTypeRequested();
      const prof = $("profileSelect").value;
      const {res, data} = await api(`/api/v1/documents/${id}/validate`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          doc_type: reqDt === "auto" ? "generic" : reqDt,
          profile_used: prof,
          feedbacks: [],
        }),
      });
      showApi(data);
      if (res.ok) toast("Version finale validée ✓", "success"); else toast(data.detail||"Échec", "error");
    } else if (action === "exporttxt") {
      const res = await fetch(`/api/v1/documents/${id}/export`, {headers:{Authorization:`Bearer ${accessToken}`}});
      const text = await res.text();
      if (res.ok) { showPreview(text); toast("Export texte prêt", "success"); } else toast("Export échoué", "error");
    } else if (action === "exportpdf") {
      toast("Génération du PDF…", "info");
      const res = await fetch(`/api/v1/documents/${id}/export-pdf`, {headers:{Authorization:`Bearer ${accessToken}`}});
      if (!res.ok) { toast("Export PDF échoué", "error"); return; }
      const blob = await res.blob();
      triggerBlobDownload(blob, `redacted_${id}.pdf`);
      toast("PDF redacté téléchargé", "success");
    } else if (action === "exportdataset") {
      const res = await fetch(`/api/v1/documents/${id}/export-dataset`, {headers:{Authorization:`Bearer ${accessToken}`}});
      const data = await res.json().catch(()=>({}));
      showApi(data);
      if (res.ok) {
        const q = data && data.quality ? data.quality : {};
        setAnonymizedPreview(id, data.anonymized_text||"Dataset exporté");
        downloadJsonFile(`dataset_${id}.json`, data);
        toast(`Dataset exporté : ${q.detections_count||0} entités. Revue requise : ${q.needs_review ? "oui" : "non"}.`, "success");
      }
      else toast("Export dataset échoué", "error");
    } else if (action === "proof") {
      const {res, data} = await api(`/api/v1/documents/${id}/proof`);
      showApi(data);
      if (res.ok) {
        showProofSummary(data);
        downloadJsonFile(`proof_${id}.json`, data);
        toast("Preuve RGPD exportée (.json)", "success");
      }
      else toast(data.detail || "Erreur preuve RGPD", "error");
    } else if (action === "exportstructured") {
      setStage("extract", "Export structured dataset en cours...");
      const {res, data} = await api(`/api/v1/documents/${id}/export-structured-dataset?doc_type=${encodeURIComponent(requestedDocType)}`);
      showApi(data);
      if (res.ok) {
        showPreview(data && data.fields ? JSON.stringify(data.fields, null, 2) : "Dataset métier exporté");
        downloadJsonFile(`structured_dataset_${id}.json`, data);
        const q = data && data.quality ? data.quality : {};
        toast(`Dataset métier exporté (${requestedDocType}) : couverture ${Math.round((q.coverage_ratio || 0) * 100)}%.`, "success");
        setStage("ready", "Extraction structurée prête.");
        await refreshMaskedSummary(id);
      } else {
        toast(data.detail || "Export dataset métier échoué", "error");
      }
    } else if (action === "exportreportdoc") {
      toast("Génération du rapport .doc…", "info");
      const res = await fetch(`/api/v1/documents/${id}/export-report-doc?doc_type=${encodeURIComponent(requestedDocType)}`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!res.ok) {
        const maybe = await res.json().catch(() => ({}));
        toast((maybe && maybe.detail) ? String(maybe.detail) : "Export rapport .doc échoué", "error");
        return;
      }
      const blob = await res.blob();
      triggerBlobDownload(blob, `rapport_confidoc_${id}.doc`);
      toast("Rapport .doc téléchargé", "success");
    } else if (action === "exportreportpdf") {
      toast("Génération du rapport .pdf…", "info");
      const res = await fetch(`/api/v1/documents/${id}/export-report-pdf?doc_type=${encodeURIComponent(requestedDocType)}`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!res.ok) {
        const maybe = await res.json().catch(() => ({}));
        toast((maybe && maybe.detail) ? String(maybe.detail) : "Export rapport .pdf échoué", "error");
        return;
      }
      const blob = await res.blob();
      triggerBlobDownload(blob, `rapport_confidoc_${id}.pdf`);
      toast("Rapport .pdf téléchargé", "success");
    } else if (action === "aisummary") {
      toast("Génération de la synthèse IA…", "info");
      const {res, data} = await api(`/api/v1/ai/summary/${id}?doc_type=${encodeURIComponent(requestedDocType)}`, {method:"POST"});
      showApi(data);
      if (!res.ok) {
        if (res.status === 409) {
          const q = data && data.quality_snapshot ? data.quality_snapshot : {};
          const miss = Array.isArray(q.critical_missing_fields) ? q.critical_missing_fields : [];
          const missTxt = miss.length ? ` Champs critiques manquants: ${miss.slice(0, 3).join(", ")}${miss.length > 3 ? "…" : ""}.` : "";
          previewOut.innerHTML = `
            <div class="ai-summary">
              <div class="ai-head">
                <div class="ai-tools"><div class="ai-mode fallback">Synthèse IA indisponible</div></div>
              </div>
              <div class="ai-status">Document non prêt IA (<b>ready_for_ai=false</b>).</div>
              <div class="ai-block">
                <div class="ai-title">Action requise</div>
                <div>Corriger/valider les champs critiques puis relancer la synthèse.${missTxt}</div>
              </div>
            </div>`;
          toast(data.detail || "Synthèse IA indisponible", "error");
          return;
        }
        toast(data.detail || "Synthèse IA échouée", "error");
        return;
      }
      let parsed = null;
      try { parsed = JSON.parse(data.summary_json_text || "{}"); } catch {}
      const summaryPayload = {
        ...data,
        summary: parsed || {},
      };
      showAiSummaryCard(summaryPayload);
      downloadJsonFile(`ai_summary_${id}.json`, {
        document_id: id,
        provider: data.provider,
        model: data.model,
        payload_policy: data.payload_policy,
        summary_source: data.summary_source || null,
        summary: parsed || data.summary_json_text || "",
      });
      toast("Synthèse IA prête (.json)", "success");
    } else if (action === "aisummary") {
      toast("Synthèse IA en cours…", "info");
      await runAiDocAction(id, "summary");
    } else if (action === "aireview") {
      toast("Analyse des points à vérifier en cours…", "info");
      await runAiDocAction(id, "review");
    } else if (action === "aidraft") {
      toast("Rédaction assistée en cours…", "info");
      await runAiDocAction(id, "draft");
    } else if (action === "askdoc") {
      if ($("docQaSelect")) $("docQaSelect").value = id;
      if ($("docQaQuestion")) $("docQaQuestion").focus();
      toast("Saisissez votre question puis cliquez « Poser la question ».", "info");
    } else if (action === "auditexport") {
      const {res, data} = await api(`/api/v1/documents/${id}/audit-export`);
      showApi(data);
      if (res.ok) {
        showAuditSummary(data);
        downloadJsonFile(`audit_${id}.json`, data);
        toast("Audit exporté (.json)", "success");
      }
      else toast(data.detail || "Erreur audit export", "error");
    } else if (action === "delete") {
      // Effacement RGPD en 2 étapes : aperçu (compteurs) puis confirmation forte.
      const {res: prevRes, data: prevData} = await api(`/api/v1/documents/${id}/deletion-preview`);
      if (!prevRes.ok) {
        toast(prevData.detail || "Impossible de charger l'aperçu suppression", "error");
        return;
      }
      showApi(prevData);
      const typed = prompt("Effacement RGPD : tapez exactement SUPPRIMER pour confirmer.");
      if (typed !== "SUPPRIMER") { toast("Suppression annulée", "info"); return; }
      const res = await fetch(`/api/v1/documents/${id}`, {method:"DELETE",headers:{Authorization:`Bearer ${accessToken}`}});
      if (res.ok) { toast("Document supprimé", "success"); showPreview("Document supprimé."); } else toast("Suppression échouée", "error");
    }
  } catch(e) {
    const msg = (e && e.message) ? e.message : "Erreur réseau";
    toast(`Erreur: ${msg}`, "error");
  }
  finally {
    setActionBusy(btn, false);
    await refreshDocs();
  }
});

// ===== TAB SWITCHING =====
function switchTab(tabName) {
  document.querySelectorAll(".nav-tab").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.tab === tabName);
  });
  document.querySelectorAll(".tab-content").forEach(el => {
    el.classList.toggle("active", el.id === `tab-${tabName}`);
  });
  if (tabName === "exports") renderExportsList();
  if (tabName === "analyse") updateActiveDocBanner();
}
document.querySelectorAll(".nav-tab").forEach(btn => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});
// Init: activer le premier onglet
switchTab("dossiers");

// ===== VALUE-PROP DISMISSIBLE =====
(function initValueProp() {
  const banner = $("valueProp");
  const dismissBtn = $("dismissValueProp");
  if (!banner || !dismissBtn) return;
  if (localStorage.getItem("confidoc_banner_dismissed") === "1") {
    banner.style.display = "none";
  }
  dismissBtn.addEventListener("click", () => {
    banner.style.display = "none";
    localStorage.setItem("confidoc_banner_dismissed", "1");
  });
})();

// ===== DOC SEARCH & FILTER =====
function applyDocFilter() {
  const search = docFilterSearch.toLowerCase().trim();
  const status = docFilterStatus;
  const items = docList.querySelectorAll(".doc-item");
  let visible = 0;
  items.forEach(el => {
    const name = (el.querySelector(".doc-name")?.textContent || "").toLowerCase();
    const statusEl = el.querySelector(".doc-status");
    const itemStatus = statusEl ? Array.from(statusEl.classList).find(c => ["uploaded","processing","ready","failed"].includes(c)) || "" : "";
    const matchSearch = !search || name.includes(search);
    const matchStatus = !status || itemStatus === status;
    el.style.display = (matchSearch && matchStatus) ? "" : "none";
    if (matchSearch && matchStatus) visible++;
  });
  // Si aucun résultat après filtre, afficher un message
  let noResult = docList.querySelector(".filter-empty");
  if (visible === 0 && currentDocs.length > 0) {
    if (!noResult) {
      noResult = document.createElement("div");
      noResult.className = "docs-empty filter-empty";
      noResult.innerHTML = '<div class="empty-icon">🔍</div><p>Aucun document ne correspond aux filtres.</p>';
      docList.appendChild(noResult);
    }
    noResult.style.display = "";
  } else if (noResult) {
    noResult.style.display = "none";
  }
}

const docSearchInput = $("docSearchInput");
const docStatusFilter = $("docStatusFilter");
if (docSearchInput) {
  docSearchInput.addEventListener("input", e => {
    docFilterSearch = e.target.value || "";
    applyDocFilter();
  });
}
if (docStatusFilter) {
  docStatusFilter.addEventListener("change", e => {
    docFilterStatus = e.target.value || "";
    applyDocFilter();
  });
}

// ===== ACTIVE DOC BANNER (onglet Analyse) =====
function updateActiveDocBanner() {
  const banner = $("activeDocBanner");
  const nameEl = $("activeDocName");
  if (!banner || !nameEl) return;
  if (!lastActiveDocId) { banner.style.display = "none"; return; }
  const doc = (currentDocs || []).find(d => d.id === lastActiveDocId);
  if (!doc) { banner.style.display = "none"; return; }
  nameEl.textContent = doc.original_filename || lastActiveDocId;
  banner.style.display = "flex";
}
const activeDocGoBtn = $("activeDocGoBtn");
if (activeDocGoBtn) {
  activeDocGoBtn.addEventListener("click", () => switchTab("dossiers"));
}

// ===== EXPORTS TAB — liste des docs prêts =====
function renderExportsList() {
  const container = $("exportDocList");
  if (!container) return;
  const readyDocs = (currentDocs || []).filter(d => d.status === "ready");
  if (!readyDocs.length) {
    container.innerHTML = `<div class="exports-empty"><span class="exports-empty-icon">📭</span><p>Aucun document prêt à exporter.<br>Traitez un document dans l'onglet <strong>Dossiers</strong>.</p></div>`;
    return;
  }
  container.innerHTML = "";
  readyDocs.forEach((doc, i) => {
    const ic = docIcon(doc.extension);
    const q = docQualityMap[doc.id] || {};
    const badge = qualityBadgeFromQuality(q);
    const item = document.createElement("div");
    item.className = "export-doc-item";
    item.style.animationDelay = `${i * 0.05}s`;
    item.innerHTML = `
      <div class="export-doc-icon ${ic.cls}">${ic.icon}</div>
      <div class="export-doc-info">
        <div class="export-doc-name" title="${doc.original_filename}">${doc.original_filename}</div>
        <div class="export-doc-meta">${formatSize(doc.size_bytes)} · <span class="doc-kpi doc-quality ${badge.cls}" style="display:inline;padding:2px 8px;font-size:11px">${badge.label}</span></div>
      </div>
      <div class="export-doc-actions">
        <button class="btn-act primary" data-a="exportreportpdf" data-id="${doc.id}">📄 PDF</button>
        <button class="btn-act" data-a="exportreportdoc" data-id="${doc.id}">📝 DOC</button>
        <button class="btn-act" data-a="exportdataset" data-id="${doc.id}">📊 CSV</button>
        <button class="btn-act" data-a="proof" data-id="${doc.id}">🛡️ RGPD</button>
      </div>`;
    container.appendChild(item);
  });
  // Délégation d'événements pour les boutons d'export dans cet onglet
  container.onclick = async (e) => {
    const btn = e.target.closest("[data-a]");
    if (!btn || !accessToken) return;
    const action = btn.dataset.a;
    const id = btn.dataset.id;
    lastActiveDocId = id || lastActiveDocId;
    const requestedDocType = currentDocTypeRequested();
    const busyLabel = { exportreportpdf: "Export...", exportreportdoc: "Export...", exportdataset: "Export...", proof: "Preuve..." }[action] || "...";
    setActionBusy(btn, true, busyLabel);
    try {
      if (action === "exportreportpdf") {
        toast("Génération PDF…", "info");
        const res = await fetch(`/api/v1/documents/${id}/export-report-pdf?doc_type=${encodeURIComponent(requestedDocType)}`, { headers: { Authorization: `Bearer ${accessToken}` } });
        if (!res.ok) { const j = await res.json().catch(() => ({})); toast(j.detail || "Erreur PDF", "error"); return; }
        triggerBlobDownload(await res.blob(), `rapport_confidoc_${id}.pdf`);
        toast("PDF téléchargé", "success");
      } else if (action === "exportreportdoc") {
        toast("Génération DOC…", "info");
        const res = await fetch(`/api/v1/documents/${id}/export-report-doc?doc_type=${encodeURIComponent(requestedDocType)}`, { headers: { Authorization: `Bearer ${accessToken}` } });
        if (!res.ok) { const j = await res.json().catch(() => ({})); toast(j.detail || "Erreur DOC", "error"); return; }
        triggerBlobDownload(await res.blob(), `rapport_confidoc_${id}.doc`);
        toast("DOC téléchargé", "success");
      } else if (action === "exportdataset") {
        toast("Export CSV en cours…", "info");
        const { res, data } = await api(`/api/v1/documents/${id}/export-dataset`);
        if (res.ok) { downloadJsonFile(`dataset_${id}.json`, data); toast("Dataset exporté", "success"); }
        else toast(data.detail || "Erreur export", "error");
      } else if (action === "proof") {
        const { res, data } = await api(`/api/v1/documents/${id}/proof`);
        if (res.ok) { downloadJsonFile(`proof_${id}.json`, data); toast("Preuve RGPD exportée", "success"); }
        else toast(data.detail || "Erreur preuve", "error");
      }
    } catch { toast("Erreur réseau", "error"); }
    finally { setActionBusy(btn, false); }
  };
}

// Refresh button in exports tab
const refreshExportsBtn = $("refreshExportsBtn");
if (refreshExportsBtn) {
  refreshExportsBtn.addEventListener("click", () => { refreshDocs(); toast("Liste actualisée", "info"); });
}

// ===== MODAL SUPPRESSION GLOBALE =====
const purgeModal = $("purgeModal");
const purgeConfirmInput = $("purgeConfirmInput");
const purgeConfirmBtn = $("purgeConfirmBtn");
const purgeCancelBtn = $("purgeCancelBtn");

function openPurgeModal() {
  if (!purgeModal) return;
  if (purgeConfirmInput) purgeConfirmInput.value = "";
  if (purgeConfirmBtn) purgeConfirmBtn.disabled = true;
  purgeModal.classList.add("active");
  setTimeout(() => { if (purgeConfirmInput) purgeConfirmInput.focus(); }, 100);
}
function closePurgeModal() {
  if (purgeModal) purgeModal.classList.remove("active");
}
if (purgeConfirmInput) {
  purgeConfirmInput.addEventListener("input", () => {
    if (purgeConfirmBtn) purgeConfirmBtn.disabled = purgeConfirmInput.value !== "SUPPRIMER";
  });
  purgeConfirmInput.addEventListener("keydown", e => {
    if (e.key === "Escape") closePurgeModal();
    if (e.key === "Enter" && purgeConfirmInput.value === "SUPPRIMER") purgeConfirmBtn && purgeConfirmBtn.click();
  });
}
if (purgeCancelBtn) purgeCancelBtn.addEventListener("click", closePurgeModal);
if (purgeModal) purgeModal.addEventListener("click", e => { if (e.target === purgeModal) closePurgeModal(); });

if (purgeConfirmBtn) {
  purgeConfirmBtn.addEventListener("click", async () => {
    closePurgeModal();
    if (!accessToken) { toast("Connectez-vous d'abord", "error"); return; }
    try {
      const { res, data } = await api(`/api/v1/documents?confirm=true`, { method: "DELETE" });
      showApi(data);
      if (res.ok) {
        const n = (data && typeof data.deleted === "number") ? data.deleted : 0;
        toast(`${n} document(s) supprimé(s)`, "success");
        showPreview("Sélectionnez un document ou uploadez un fichier.");
        if (maskedOut) maskedOut.textContent = "Aucun document.";
        lastAnonDocId = null; lastAnonText = "";
        lastOriginalDocId = null; lastOriginalText = "";
        await refreshDocs();
      } else {
        toast((data && data.detail) ? String(data.detail) : "Échec suppression", "error");
      }
    } catch { toast("Erreur réseau", "error"); }
  });
}

// ===== STREAMING IA =====
let activeStreamReader = null;

async function startAiStream() {
  const docId = lastActiveDocId;
  if (!docId) { toast("Sélectionnez d'abord un document dans Dossiers", "error"); return; }
  if (!accessToken) { toast("Connectez-vous d'abord", "error"); return; }

  const question = ($("streamQuestion") || {}).value || "";
  const output = $("streamOutput");
  const startBtn = $("startStreamBtn");
  const stopBtn = $("stopStreamBtn");

  if (output) { output.style.display = "block"; output.innerHTML = '<span class="ai-cursor"></span>'; }
  if (startBtn) startBtn.disabled = true;
  if (stopBtn) stopBtn.style.display = "";

  let accumulated = "";
  try {
    const url = `/api/v1/ai/stream/${docId}${question ? "?question=" + encodeURIComponent(question) : ""}`;
    const resp = await fetch(url, {
      method: "POST",
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      toast(err.detail || "Erreur streaming IA", "error");
      return;
    }
    const reader = resp.body.getReader();
    activeStreamReader = reader;
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const raw = line.slice(6).trim();
        if (raw === "[DONE]") break;
        try {
          const parsed = JSON.parse(raw);
          if (parsed.error) { toast(parsed.error, "error"); break; }
          if (parsed.chunk) {
            accumulated += parsed.chunk;
            if (output) output.innerHTML = accumulated.replace(/\n/g, "<br>") + '<span class="ai-cursor"></span>';
          }
        } catch {}
      }
    }
    if (output) output.innerHTML = accumulated.replace(/\n/g, "<br>");
    toast("Synthèse générée", "success");
  } catch (e) {
    if (e.name !== "AbortError") toast("Erreur streaming: " + e.message, "error");
  } finally {
    activeStreamReader = null;
    if (startBtn) startBtn.disabled = false;
    if (stopBtn) stopBtn.style.display = "none";
  }
}

function stopAiStream() {
  if (activeStreamReader) {
    activeStreamReader.cancel();
    activeStreamReader = null;
  }
  const stopBtn = $("stopStreamBtn");
  const startBtn = $("startStreamBtn");
  if (stopBtn) stopBtn.style.display = "none";
  if (startBtn) startBtn.disabled = false;
}

const startStreamBtn = $("startStreamBtn");
const stopStreamBtn = $("stopStreamBtn");
if (startStreamBtn) startStreamBtn.addEventListener("click", startAiStream);
if (stopStreamBtn) stopStreamBtn.addEventListener("click", stopAiStream);
const streamQuestionInput = $("streamQuestion");
if (streamQuestionInput) {
  streamQuestionInput.addEventListener("keydown", e => { if (e.key === "Enter") startAiStream(); });
}

// ===== KEYBOARD SHORTCUTS =====
const shortcutsModal = $("shortcutsModal");
const closeShortcutsBtn = $("closeShortcutsBtn");
if (closeShortcutsBtn) closeShortcutsBtn.addEventListener("click", () => shortcutsModal && shortcutsModal.classList.remove("active"));
if (shortcutsModal) shortcutsModal.addEventListener("click", e => { if (e.target === shortcutsModal) shortcutsModal.classList.remove("active"); });

document.addEventListener("keydown", (e) => {
  // Ignore when typing in inputs
  const tag = (e.target || {}).tagName || "";
  if (["INPUT", "TEXTAREA", "SELECT"].includes(tag)) return;
  // Ignore when a modal is open (except Escape)
  const modalOpen = document.querySelector(".modal-overlay.active");

  if (e.key === "Escape") {
    if (shortcutsModal && shortcutsModal.classList.contains("active")) { shortcutsModal.classList.remove("active"); return; }
    closePurgeModal();
    stopAiStream();
    return;
  }
  if (modalOpen) return;

  if (e.key === "1") { e.preventDefault(); switchTab("dossiers"); }
  else if (e.key === "2") { e.preventDefault(); switchTab("analyse"); }
  else if (e.key === "3") { e.preventDefault(); switchTab("exports"); }
  else if (e.key === "r" || e.key === "R") { e.preventDefault(); refreshDocs(); toast("Actualisé", "info"); }
  else if (e.key === "?") { e.preventDefault(); if (shortcutsModal) shortcutsModal.classList.add("active"); }
});

window.addEventListener("error", (ev) => {
  const msg = (ev && ev.message) ? ev.message : "Erreur JavaScript";
  toast(`Erreur UI: ${msg}`, "error");
});
window.addEventListener("unhandledrejection", (ev) => {
  const reason = ev && ev.reason ? String(ev.reason) : "Promesse rejetée";
  toast(`Erreur async: ${reason}`, "error");
});
