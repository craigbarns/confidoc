let accessToken = "";
let currentDocs = [];
let docDetectionMap = {};
let lastAnonDocId = null;
let lastAnonText = "";
let lastOriginalDocId = null;
let lastOriginalText = "";
let previewMode = "anon"; // "anon" | "beforeafter"
let docExtractionDetails = {};

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
  const modeFallback = (data && data.summary_source) === "fallback_local";
  const modeText = modeFallback ? "Mode : synthèse de secours" : "Mode : synthèse assistée";
  const modeClass = modeFallback ? "fallback" : "ok";
  const conf = Number(s.confiance_globale || 0);
  const points = Array.isArray(s.points_cles) ? s.points_cles : [];
  const alerts = Array.isArray(s.anomalies_ou_alertes) ? s.anomalies_ou_alertes : [];
  const questions = Array.isArray(s.questions_de_revue) ? s.questions_de_revue : [];
  const resume = s.resume_executif || "Synthèse générée avec prudence à partir des données disponibles. Une revue humaine reste recommandée.";
  const q = data && data.quality_snapshot ? data.quality_snapshot : {};
  const docStatus = q.ready_for_ai ? "Prêt IA" : (q.needs_review ? "À revoir" : "En analyse");
  const listHtml = arr => arr.map(x => `<li>${String(x)}</li>`).join("");
  const summaryTextForCopy = [
    "Synthèse IA",
    `Mode: ${modeFallback ? "synthèse de secours" : "synthèse assistée"}`,
    `Confiance: ${confidenceLabel(conf)} (${Math.round(conf * 100)}%)`,
    `Statut du document: ${docStatus}`,
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
      if (experienceHeadline) return experienceHeadline;
      if (!quality.needs_review) return "Aucun point qualité bloquant détecté.";
      if (qualityFlagsCount > 0) return `${qualityFlagsCount} point(s) qualité à revoir avant validation.`;
      return "Revue manuelle ciblée recommandée.";
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
    const reviewDetails = rawFlags.length
      ? rawFlags.map(f => `- ${FLAG_LABELS[f] || f}`).join("\n")
      : "- Aucun point de revue détecté";
    const criticalDetails = criticalMissing.length
      ? criticalMissing.map(f => `- ${labelCriticalField(f)} (${f})`).join("\n")
      : "- Aucun champ critique manquant";
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
          <div class="proof-card-title">À revoir</div>
          <div class="proof-card-value">${quality.needs_review ? "Revue recommandée" : "Aucune revue requise"}</div>
          <div class="proof-card-sub">${qualityLabel()}</div>
          ${experienceSeg ? `<div class="proof-card-sub" style="opacity:0.92;font-size:0.9em">${experienceSeg}</div>` : ""}
          <div class="proof-card-sub" style="white-space:pre-wrap">${reviewDetails}</div>
          <div class="proof-card-sub" style="margin-top:6px;font-weight:700">Champs critiques manquants</div>
          <div class="proof-card-sub" style="white-space:pre-wrap">${criticalDetails}</div>
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

async function api(path, opts={}) {
  const headers = opts.headers || {};
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
  const res = await fetch(path, {...opts, headers});
  const raw = await res.text();
  let data;
  try { data = raw ? JSON.parse(raw) : {}; } catch { data = {raw}; }
  return {res, data};
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
  currentDocs.forEach((doc, i) => {
    const ic = docIcon(doc.extension);
    const el = document.createElement("div");
    el.className = "doc-item";
    el.style.animationDelay = `${i*0.05}s`;
    el.innerHTML = `
      <div class="doc-icon ${ic.cls}">${ic.icon}</div>
      <div class="doc-info">
        <div class="doc-name" title="${doc.original_filename}">${doc.original_filename}</div>
        <div class="doc-meta"><span>${formatSize(doc.size_bytes)}</span><span class="doc-status ${doc.status}">${statusLabel(doc.status)}</span></div>
        <div class="doc-kpis">
          <span class="doc-kpi" data-doc-detection="${doc.id}">${docDetectionMap[doc.id] != null ? `entités: ${docDetectionMap[doc.id]}` : "entités: —"}</span>
        </div>
        <div class="doc-next">${nextAction(doc)}</div>
        <div class="doc-actions">
          <button class="btn-act success" data-a="processall" data-id="${doc.id}">🚀 Traiter</button>
          <button class="btn-act success" data-a="validate" data-id="${doc.id}">✓ Valider</button>
          <button class="btn-act" data-a="rerunextract" data-id="${doc.id}">🔁 Relancer l'extraction</button>
          <button class="btn-act primary" data-a="exportstructured" data-id="${doc.id}">📤 Exporter</button>
          <details class="expert-only">
            <summary class="btn-act" style="display:inline-flex;list-style:none">Plus</summary>
            <div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:6px">
              <button class="btn-act" data-a="anonymize" data-id="${doc.id}">🔒 Anonymiser</button>
              <button class="btn-act" data-a="preview" data-id="${doc.id}">👁️ Prévisualiser</button>
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
  });
}

async function refreshDocs() {
  if (!accessToken) return;
  try {
    const {res, data} = await api("/api/v1/documents");
    showApi(data);
    if (res.ok) {
      renderDocs(data);
      await refreshDocDetections(data);
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
  }
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

// Upload drag & drop
const dropZone = $("dropZone");
const fileInput = $("fileInput");
["dragenter","dragover"].forEach(ev => dropZone.addEventListener(ev, e => { e.preventDefault(); dropZone.classList.add("dragover"); }));
["dragleave","drop"].forEach(ev => dropZone.addEventListener(ev, e => { e.preventDefault(); dropZone.classList.remove("dragover"); }));
dropZone.addEventListener("drop", e => { if (e.dataTransfer.files.length) { fileInput.files = e.dataTransfer.files; doUpload(); } });
fileInput.addEventListener("change", () => { if (fileInput.files.length) doUpload(); });

async function doUpload() {
  if (!accessToken) { toast("Connectez-vous d'abord", "error"); return; }
  const file = fileInput.files[0];
  if (!file) return;
  const prog = $("uploadProgress");
  const fill = $("progressFill");
  const progText = $("progText");
  prog.classList.add("active");
  fill.style.width = "30%";
  progText.textContent = `Upload de ${file.name}…`;

  const form = new FormData();
  form.append("file", file);
  const profile = $("profileSelect").value;
  const requestedDocType = currentDocTypeRequested();
  const auto = $("autoAnonymize").checked;

  try {
    setStage("upload", "Upload du document en cours...");
    fill.style.width = "60%";
    const {res, data} = await api(`/api/v1/uploads?auto_anonymize=${auto}&profile=${encodeURIComponent(profile)}&document_type=${encodeURIComponent(requestedDocType)}`, {method:"POST", body:form});
    showApi(data);
    if (!res.ok) {
      toast(`Upload échoué: ${data.detail||res.status}`, "error");
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
  } catch(e) { toast("Erreur réseau", "error"); }
  finally { setTimeout(() => { prog.classList.remove("active"); fill.style.width = "0"; fill.style.background = ""; }, 2500); fileInput.value = ""; }
}

// Refresh
$("refreshBtn").addEventListener("click", () => { refreshDocs(); toast("Liste actualisée", "info"); });

const purgeAllBtn = $("purgeAllDocsBtn");
if (purgeAllBtn) {
  purgeAllBtn.addEventListener("click", async () => {
    if (!accessToken) { toast("Connectez-vous d'abord", "error"); return; }
    if (!confirm("Supprimer définitivement TOUS vos documents ? Cette action est irréversible.")) return;
    if (prompt("Pour confirmer, tapez exactement : VIDER") !== "VIDER") {
      toast("Suppression annulée", "info");
      return;
    }
    try {
      const { res, data } = await api(`/api/v1/documents?confirm=true`, { method: "DELETE" });
      showApi(data);
      if (res.ok) {
        const n = (data && typeof data.deleted === "number") ? data.deleted : 0;
        toast(`${n} document(s) supprimé(s)`, "success");
        showPreview("Sélectionnez un document ou uploadez un fichier.");
        if (maskedOut) maskedOut.textContent = "Aucun document.";
        lastAnonDocId = null;
        lastAnonText = "";
        lastOriginalDocId = null;
        lastOriginalText = "";
        await refreshDocs();
      } else {
        toast((data && data.detail) ? String(data.detail) : "Échec suppression", "error");
      }
    } catch (e) {
      toast("Erreur réseau", "error");
    }
  });
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

// Document actions
docList.addEventListener("click", async e => {
  const btn = e.target.closest("[data-a]");
  if (!btn || !accessToken) return;
  const action = btn.dataset.a;
  const id = btn.dataset.id;
  const profile = $("profileSelect").value;
  const requestedDocType = currentDocTypeRequested();
  const busyLabelByAction = {
    processall: "Traitement...",
    anonymize: "Anonymisation...",
    rerunextract: "Relance...",
    preview: "Chargement...",
    validate: "Validation...",
    exportstructured: "Export...",
    exportdataset: "Export...",
    aisummary: "Synthèse...",
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
      const {res, data} = await api(`/api/v1/documents/${id}/anonymize?profile=${encodeURIComponent(profile)}&document_type=${encodeURIComponent(requestedDocType)}`, {method:"POST"});
      showApi(data);
      if (res.ok) {
        setAnonymizedPreview(id, data.preview_text||"");
        setDetections(data.detections_count||0, "dernier document traité");
        setDocDetection(id, data.detections_count||0);
        toast(`Extraction relancée (${requestedDocType})`, "success");
        setStage("extract", `Extraction relancée (${requestedDocType}) terminée.`);
      } else {
        toast(data.detail || "Relance extraction échouée", "error");
      }
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
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href=url; a.download=`redacted_${id}.pdf`; a.click(); URL.revokeObjectURL(url);
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
    } else if (action === "aisummary") {
      toast("Génération de la synthèse IA…", "info");
      const {res, data} = await api(`/api/v1/ai/summary/${id}?doc_type=${encodeURIComponent(requestedDocType)}`, {method:"POST"});
      showApi(data);
      if (!res.ok) {
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

window.addEventListener("error", (ev) => {
  const msg = (ev && ev.message) ? ev.message : "Erreur JavaScript";
  toast(`Erreur UI: ${msg}`, "error");
});
window.addEventListener("unhandledrejection", (ev) => {
  const reason = ev && ev.reason ? String(ev.reason) : "Promesse rejetée";
  toast(`Erreur async: ${reason}`, "error");
});
