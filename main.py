"""
Automation Fit
"""
import os
import csv
from io import StringIO
from flask import Flask, render_template, request, redirect, url_for, jsonify, Response
from sqlalchemy import text

# Imports für Datenbank
from extensions import db
from models.database import (
    QuestionnaireVersion, Dimension, Question, ScaleOption,
    Process, Assessment, Answer, DimensionResult, TotalResult, Hint, QuestionCondition,
    SharedDimensionAnswer, EconomicMetric
)
from services.scoring_service import ScoringService
from seed_data import seed_data

# App-Konfiguration
app = Flask(__name__)

# Jinja2-Filter für Frage-Trennung
def question_regex(text):
    """Teilt eine Frage in Haupttext und Zusatzinformationen auf."""
    info_patterns = [
        'Trifft voll zu:', 'Trifft gar nicht zu:', 'Ja:', 'Nein:', 'Achtung:'
    ]
    info_start = None
    for pat in info_patterns:
        idx = text.find(pat)
        if idx != -1:
            info_start = idx
            break
    if info_start is not None:
        main = text[:info_start].strip()
        # Entferne einzelne öffnende oder schließende Klammer am Ende des Hauptsatzes
        if main.endswith('('):
            main = main[:-1].strip()
        if main.endswith(')'):
            main = main[:-1].strip()
        info = text[info_start:].strip()
        # Klammern am Anfang und/oder Ende entfernen
        if info.startswith('('):
            info = info[1:].strip()
        if info.endswith(')'):
            info = info[:-1].strip()
        return {'main': main, 'info': info}
    else:
        return {'main': text, 'info': ''}
app.jinja_env.filters['question_regex'] = question_regex

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(BASE_DIR, 'data', 'decision_support.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialisiere Datenbank
db.init_app(app)

# Hilfsfunktion: Datenbank initialisieren
def init_database():
    """Erstellt Tabellen und lädt Testdaten"""
    with app.app_context():
        db.create_all()
        migrate_shared_dimension_answer_constraint()
        seed_data()


def migrate_shared_dimension_answer_constraint():
    """Migriert alte UNIQUE-Constraint für 
    shared_dimension_answer auf (dimension_id, 
    question_id, scale_option_id)."""
    table_sql = db.session.execute(
        text("SELECT sql FROM sqlite_master WHERE type='table' AND name='shared_dimension_answer'")
    ).scalar()

    if not table_sql:
        return

    normalized_sql = " ".join(table_sql.replace("\n", " ").split()).lower()
    has_old_constraint = "unique (dimension_id, question_id)" in normalized_sql
    has_new_constraint = "unique (dimension_id, question_id, scale_option_id)" in normalized_sql

    if not has_old_constraint or has_new_constraint:
        return

    db.session.execute(text("ALTER TABLE shared_dimension_answer " \
    "RENAME TO shared_dimension_answer_old"))
    db.session.commit()

    SharedDimensionAnswer.__table__.create(bind=db.engine)

    db.session.execute(text("""
        INSERT OR IGNORE INTO shared_dimension_answer
            (id, dimension_id, question_id, scale_option_id, numeric_value, updated_at)
        SELECT
            id, dimension_id, question_id, scale_option_id, numeric_value, updated_at
        FROM shared_dimension_answer_old
    """))
    db.session.execute(text("DROP TABLE shared_dimension_answer_old"))
    db.session.commit()


def build_answers_map(assessment_id: int):
    """
    Rückgabe:
      answers_map[qid] = {
        "numeric": float|None,
        "single": int|None,
        "multi": [int, ...]   }
    """
    rows = Answer.query.filter_by(assessment_id=assessment_id).all()
    answers_map = {}

    for a in rows:
        qid = a.question_id
        if qid not in answers_map:
            answers_map[qid] = {"numeric": None, "single": None, "multi": []}

        if a.numeric_value is not None:
            answers_map[qid]["numeric"] = a.numeric_value
        if a.scale_option_id is not None:
            answers_map[qid]["multi"].append(a.scale_option_id)
            answers_map[qid]["single"] = a.scale_option_id

    for qid in answers_map:
        answers_map[qid]["multi"] = sorted(list(set(answers_map[qid]["multi"])))

    return answers_map


def build_hints_map(questionnaire_version_id: int):
    """
    Rückgabe:
      hints_map[qid][option_id] = [{"text": "...", "type": "info|warning|error"}, ...]
    """
    hints = (
        Hint.query
        .join(Question, Hint.question_id == Question.id)
        .filter(Question.questionnaire_version_id == questionnaire_version_id)
        .all()
    )

    hints_map = {}
    for h in hints:
        qid = h.question_id
        opt_id = h.scale_option_id
        if qid not in hints_map:
            hints_map[qid] = {}
        if opt_id is None:
            continue
        hints_map[qid].setdefault(opt_id, []).append({
            "text": h.hint_text,
            "type": h.hint_type
        })
    return hints_map

# Gemeinsame Dimensionen - Hilfsfunktionen
def get_shared_dimension_ids():
    """Gibt die IDs der Dimensionen zurück, die gemeinsam gespeichert werden können (Dim 1 & 2)"""
    qv = QuestionnaireVersion.query.filter_by(is_active=True).first()
    if not qv:
        return []
    # Nur Dimensionen 1 (Plattformverfügbarkeit) und 2 (Organisatorisch) shared
    dimensions = Dimension.query.filter_by(
        questionnaire_version_id=qv.id
    ).filter(
        Dimension.code.in_(['1','2'])
    ).all()
    return [d.id for d in dimensions]


def load_shared_dimension_answers(dimension_id):
    """Lädt gemeinsame Antworten für eine Dimension"""
    shared_answers = SharedDimensionAnswer.query.filter_by(
        dimension_id=dimension_id
    ).all()
    answers_map = {}
    for sa in shared_answers:
        qid = sa.question_id
        if qid not in answers_map:
            answers_map[qid] = {"numeric": None, "single": None, "multi": []}

        if sa.numeric_value is not None:
            answers_map[qid]["numeric"] = sa.numeric_value
        if sa.scale_option_id is not None:
            answers_map[qid]["multi"].append(sa.scale_option_id)
            answers_map[qid]["single"] = sa.scale_option_id

    return answers_map


def save_shared_dimension_answers(dimension_id, answers_data):
    """
    Speichert Antworten einer Dimension als gemeinsame Antworten.
    answers_data ist ein dict: {question_id: {'numeric': ..., 'single': ..., 'multi': [...]}}
    """
    # Lösche alte gemeinsame Antworten für diese Dimension
    SharedDimensionAnswer.query.filter_by(dimension_id=dimension_id).delete()
    # Speichere neue gemeinsame Antworten
    for question_id, answer_info in answers_data.items():
        numeric_val = answer_info.get('numeric')
        single_val = answer_info.get('single')
        multi_vals = answer_info.get('multi', [])
        if numeric_val is not None:
            # Numerische Antwort
            shared_answer = SharedDimensionAnswer(
                dimension_id=dimension_id,
                question_id=question_id,
                numeric_value=numeric_val
            )
            db.session.add(shared_answer)
        elif single_val is not None:
            # Single-Choice Antwort
            shared_answer = SharedDimensionAnswer(
                dimension_id=dimension_id,
                question_id=question_id,
                scale_option_id=single_val
            )
            db.session.add(shared_answer)
        elif multi_vals:
            # Multiple-Choice: Eine Zeile pro gewählter Option speichern
            unique_multi_vals = list(dict.fromkeys(multi_vals))
            for opt_id in unique_multi_vals:
                shared_answer = SharedDimensionAnswer(
                    dimension_id=dimension_id,
                    question_id=question_id,
                    scale_option_id=opt_id
                )
                db.session.add(shared_answer)

def serialize_question(question: Question, answers_map: dict, hints_map: dict):
    """Serialisiert eine Frage mit ihren Optionen, 
    Antworten und Bedingungen für die Frontend-Darstellung."""
    options = []
    if question.scale_id:
        opts = (
            ScaleOption.query
            .filter_by(scale_id=question.scale_id)
            .order_by(ScaleOption.sort_order.asc())
            .all()
        )
        options = [{
            "id": o.id,
            "code": o.code,
            "label": o.label,
            "is_na": bool(o.is_na),
        } for o in opts]

    # Answer aus answers_map
    ans = answers_map.get(question.id, {"numeric": None, "single": None, "multi": []})

    if question.question_type == "number":
        answer_value = ans["numeric"]
    elif question.question_type == "multiple_choice":
        answer_value = ans["multi"]  # Liste
    else:
        answer_value = ans["single"]  # single_choice

    # Conditions
    conds = (
        QuestionCondition.query
        .filter_by(question_id=question.id)
        .order_by(QuestionCondition.sort_order.asc())
        .all()
    )
    conditions = [{"question_id": c.depends_on_question_id,
                   "option_id": c.depends_on_option_id} for c in conds]

    legacy_dep_q = question.depends_on_question_id
    legacy_dep_opt = question.depends_on_option_id
    if not conditions and legacy_dep_q and legacy_dep_opt:
        conditions = [{"question_id": legacy_dep_q, "option_id": legacy_dep_opt}]

    question_dict = {
        "id": question.id,
        "code": question.code,
        "text": question.text,

        "type": question.question_type,
        "unit": question.unit,
        "sort_order": question.sort_order,

        "options": options,
        "answer": answer_value,

        "hints": hints_map.get(question.id, {}),

        "depends_logic": getattr(question, "depends_logic", "all"),
        "conditions": conditions,

        "depends_on": legacy_dep_q,
        "depends_on_option": legacy_dep_opt,
    }

    return question_dict


# Hilfsfunktion: Filterlogik anwenden
def apply_filter_logic(assessment_id):
    """
    Wendet die Filterlogik an und setzt is_applicable für alle Antworten basierend auf Bedingungen.
    
    Die Funktion:
    1. Lädt alle Fragen und Antworten für das Assessment
    2. Baut eine Map der beantworteten Optionen auf
    3. Evaluiert für jede Frage, ob sie anwendbar ist (basierend auf Bedingungen)
    4. Setzt das is_applicable Flag entsprechend
    5. Iteriert mehrfach, um Kaskaden-Abhängigkeiten zu behandeln
    """
    assessment = db.session.get(Assessment, assessment_id)
    if not assessment:
        return

    # Alle Fragen für diese Questionnaire Version
    all_questions = Question.query.filter_by(
        questionnaire_version_id=assessment.questionnaire_version_id
    ).order_by(Question.dimension_id, Question.sort_order).all()

    def get_conditions(q):
        """Liefert alle Bedingungen für eine Frage (neu + legacy)"""
        if q.conditions:
            return [(c.depends_on_question_id, c.depends_on_option_id) for c in q.conditions]
        if q.depends_on_question_id and q.depends_on_option_id:
            return [(q.depends_on_question_id, q.depends_on_option_id)]
        return []

    def build_answer_map():
        """
        Baut eine Map: question_id -> set(selected_option_ids)
        Nur für is_applicable=True Antworten
        """
        answers = Answer.query.filter_by(
            assessment_id=assessment_id,
            is_applicable=True
        ).all()

        answer_map = {}
        for ans in answers:
            qid = ans.question_id
            if qid not in answer_map:
                answer_map[qid] = set()
            if ans.scale_option_id is not None:
                answer_map[qid].add(ans.scale_option_id)

        return answer_map

    def evaluate_applicable(q, answer_map):
        """
        Prüft, ob eine Frage anwendbar ist basierend auf ihren Bedingungen
        """
        conds = get_conditions(q)

        # Keine Bedingungen = immer anwendbar
        if not conds:
            return True

        # Logik: "all" oder "any"
        logic = getattr(q, 'depends_logic', 'all').lower()

        # Prüfe jede Bedingung
        results = []
        for parent_q_id, required_opt_id in conds:
            # Wurde die erforderliche Option für die parent-Frage gewählt?
            is_met = required_opt_id in answer_map.get(parent_q_id, set())
            results.append(is_met)

        # Wende Logik an
        if logic == "any":
            return any(results)  # Mindestens eine Bedingung erfüllt
        else:  # "all"
            return all(results)  # Alle Bedingungen erfüllt

    # Iterative Anwendung (für Kaskaden-Abhängigkeiten)
    max_iterations = 10
    iteration = 0
    changes_made = True

    while changes_made and iteration < max_iterations:
        iteration += 1
        changes_made = False

        # Aktuelle Antwort-Map bauen
        answer_map = build_answer_map()

        # Für jede Frage prüfen
        for question in all_questions:
            # Ist die Frage anwendbar?
            should_be_applicable = evaluate_applicable(question, answer_map)

            # Hole alle Antworten für diese Frage
            answers = Answer.query.filter_by(
                assessment_id=assessment_id,
                question_id=question.id
            ).all()

            # Update is_applicable wenn nötig
            for answer in answers:
                if answer.is_applicable != should_be_applicable:
                    answer.is_applicable = should_be_applicable
                    changes_made = True

                    # Wenn Frage nicht mehr anwendbar, lösche die Antwort-Werte
                    if not should_be_applicable:
                        answer.scale_option_id = None
                        answer.numeric_value = None



# Hilfsfunktion: Dimension Status berechnen
def get_dimension_status(dimension_id, assessment_id=None):
    """
    Berechnet Status einer Dimension
    
    Returns:
        - 'not_started': Keine Frage beantwortet
        - 'partial': Einige Fragen beantwortet
        - 'complete': Alle Fragen beantwortet
    """

    questions = Question.query.filter_by(dimension_id=dimension_id).all()
    total_questions = len(questions)

    if total_questions == 0:
        return 'not_started'

    if not assessment_id:
        return 'not_started'
    # Zähle beantwortete Fragen
    answered_count = 0

    for question in questions:
        answer = Answer.query.filter_by(
            assessment_id=assessment_id,
            question_id=question.id,
            is_applicable=True
        ).first()

        if not answer:
            continue

        # Prüfe ob beantwortet
        if question.question_type == 'number':
            if answer.numeric_value is not None:
                answered_count += 1
        else:
            if answer.scale_option_id is not None:
                answered_count += 1

    if answered_count == 0:
        return 'not_started'
    elif answered_count == total_questions:
        return 'complete'
    else:
        return 'partial'

# Route: Startseite (Fragebogen)
@app.route('/')
def index():
    """Zeigt den Fragebogen an"""

    qv = QuestionnaireVersion.query.filter_by(is_active=True).first()
    if not qv:
        return "Keine aktive Fragebogen-Version gefunden", 500

    dimensions = Dimension.query.filter_by(
        questionnaire_version_id=qv.id
    ).order_by(Dimension.sort_order).all()

    hints_map = build_hints_map(qv.id)
    shared_dim_ids = get_shared_dimension_ids()

    # Für jede Dimension: Fragen laden
    for dim in dimensions:
        questions = Question.query.filter_by(
            dimension_id=dim.id
        ).order_by(Question.sort_order).all()

        # Lade gemeinsame Antworten für Dimensionen 1 & 2
        if dim.id in shared_dim_ids:
            answers_map = load_shared_dimension_answers(dim.id)
        else:
            answers_map = {}

        # Serialize Fragen in separates Attribut (nicht die SQLAlchemy relationship ändern)
        dim.serialized_questions = [serialize_question(q,
                                                       answers_map,
                                                       hints_map)
                                                       for q in questions]

        # Markiere Dimension als "gemeinsam nutzbar"
        dim.is_shared = dim.id in shared_dim_ids

    return render_template(
        'index.html',
        questionnaire=qv,
        dimensions=dimensions,
        edit_mode=False
    )

@app.route('/assessment/<int:assessment_id>/edit')
def edit_assessment(assessment_id):
    """Zeigt Fragebogen zum Bearbeiten eines Assessments"""

    assessment = Assessment.query.get_or_404(assessment_id)
    process = db.session.get(Process, assessment.process_id)
    qv = db.session.get(QuestionnaireVersion, assessment.questionnaire_version_id)

    dimensions = Dimension.query.filter_by(
        questionnaire_version_id=qv.id
    ).order_by(Dimension.sort_order).all()

    # IM EDIT-MODUS: Lade IMMER die Antworten aus dem Assessment
    answers_map = build_answers_map(assessment_id)
    hints_map = build_hints_map(qv.id)
    shared_dim_ids = get_shared_dimension_ids()

    # Für jede Dimension: Fragen laden
    for dim in dimensions:
        questions = Question.query.filter_by(
            dimension_id=dim.id
        ).order_by(Question.sort_order).all()

        # Im Edit-Modus: Verwende immer die answers_map vom Assessment
        dim.serialized_questions = [serialize_question(q,
                                                       answers_map,
                                                       hints_map)
                                                       for q in questions]

        # Markiere Dimension als "gemeinsam nutzbar"
        dim.is_shared = dim.id in shared_dim_ids

    process_data = {
        "name": process.name,
        "description": process.description,
        "industry": process.industry
    }

    return render_template(
        'index.html',
        questionnaire=qv,
        dimensions=dimensions,
        edit_mode=True,
        process_data=process_data,
        assessment_id=assessment.id
    )
def generate_dimension_recommendations(
    dimension_code,
    dimension_name,
    rpa_score,
    ipa_score,
    rpa_excluded,
    ipa_excluded
):
    """
    Generiert Empfehlungen für eine Dimension basierend auf den Scores.

    Returns:
        dict mit:
          - 'rpa_recommendation' (oder None)
          - 'ipa_recommendation' (oder None)
          - optional: 'overall_recommendation' (RPA vs IPA Hinweis)
        Jede Empfehlung ist ein dict mit:
          'type', 'icon', 'color', 'title', 'text', 'actions'
    """


    # 1) Feinere Score-Klassen
    SCORE_BANDS = [
        # max ist exklusiv
        {"key": "critical", "max": 1.5, "type": "error",
         "icon": "🛑", "color": "#ef4444", "title": "Kritisch"},
        {"key": "high",     "max": 2.5, "type": "error",
         "icon": "⚠️", "color": "#ef4444", "title": "Hohes Risiko"},
        {"key": "medium",   "max": 3.3, "type": "warning",
         "icon": "⚡", "color": "#f59e0b", "title": "Verbesserungsbedarf"},
        {"key": "good",     "max": 4.2, "type": "info",
         "icon": "✅", "color": "#3b82f6", "title": "Solide Basis"},
        {"key": "excellent","max": 5.1, "type": "success",
         "icon": "🌟", "color": "#22c55e", "title": "Sehr gut"},
    ]

    def classify(score):
        for band in SCORE_BANDS:
            if score < band["max"]:
                return band
        return SCORE_BANDS[-1]

    # 2) Text-/Action-Bibliothek je Dimension (RPA/IPA differenziert)
    # Prinzip: pro Dimension + Band ein Fokus + handlungsnahe Schritte.
    REC_LIBRARY = build_recommendation_library()

    def build_reco(d_code, d_name, a_type, score, band_key, band_meta):
        # Dimension fallback (wenn nicht gemappt)
        dim_cfg = REC_LIBRARY.get(d_code, REC_LIBRARY["_fallback"])
        band_cfg = dim_cfg.get(band_key, dim_cfg["_fallback_band"])

        # band_cfg kann entweder:
        # - dict mit 'text'/'actions' sein
        # - dict mit 'RPA'/'IPA' Unterscheidung sein
        if "RPA" in band_cfg or "IPA" in band_cfg:
            type_cfg = band_cfg.get(a_type, band_cfg.get("_fallback_type"))
        else:
            type_cfg = band_cfg

        # Falls das Mapping doch unvollständig ist:
        text = type_cfg.get("text") if isinstance(type_cfg, dict) else None
        actions = type_cfg.get("actions") if isinstance(type_cfg, dict) else None

        if not text:
            text = (
                f"{d_name}: Score {score:.1f}/5 → {band_meta['title']}. "
                f"Bitte Antworten prüfen und gezielte Verbesserungen ableiten."
            )
        else:
            # leichte Personalisierung
            text = text.format(
                dimension_code=d_code,
                dimension_name=d_name,
                automation_type=a_type,
                score=f"{score:.1f}"
            )

        if not actions:
            actions = default_actions_for_band(band_key, a_type)

        return {
            "type": band_meta["type"],
            "icon": band_meta["icon"],
            "color": band_meta["color"],
            "title": f"{d_name}: {band_meta['title']} ({score:.1f}/5)",
            "text": text,
            "actions": actions,
        }

    # 3) Ergebnis zusammenbauen (RPA/IPA einzeln + optional Overall)
    result = {
        "rpa_recommendation": None,
        "ipa_recommendation": None,
        "overall_recommendation": None, 
    }

    # RPA
    if rpa_excluded:
        result["rpa_recommendation"] = {
            "type": "error",
            "icon": "❌",
            "color": "#ef4444",
            "title": f"{dimension_name}: RPA ausgeschlossen",
            "text": "RPA wurde für diese Dimension ausgeschlossen. Prüfen Sie"
            " die Ausschlusskriterien und ob Alternativen (IPA/Teilautomatisierung) sinnvoll sind.",
            "actions": [
                "Ausschlusskriterium(e) konkret benennen (welche Antwort triggert?)",
                "Prüfen, ob Prozess/Plattform durch kleine Änderungen RPA-fähig wird",
                "Falls nicht: IPA oder API-/Integrationslösung evaluieren",
            ],
        }
    elif rpa_score is not None:
        band = classify(rpa_score)
        result["rpa_recommendation"] = build_reco(dimension_code,
                                                  dimension_name, "RPA",
                                                  rpa_score, band["key"],
                                                  band)
    else:
        # optional: wenn Score fehlt
        result["rpa_recommendation"] = {
            "type": "info",
            "icon": "ℹ️",
            "color": "#3b82f6",
            "title": f"{dimension_name}: RPA nicht bewertet",
            "text": "Für RPA liegt in dieser Dimension kein Score vor "
            "(None). Prüfen Sie, ob die Dimension beantwortet/bewertet wurde.",
            "actions": ["Bewertungslogik prüfen (None vs. '-')", 
                        "Fehlende Antworten nachziehen", "Seed/Skala validieren"],
        }

    # IPA
    if ipa_excluded:
        result["ipa_recommendation"] = {
            "type": "error",
            "icon": "❌",
            "color": "#ef4444",
            "title": f"{dimension_name}: IPA ausgeschlossen",
            "text": "IPA wurde für diese Dimension ausgeschlossen. "
            "Prüfen Sie die Ausschlusskriterien und ob RPA/Teilautomatisierung sinnvoll ist.",
            "actions": [
                "Ausschlusskriterium(e) konkret benennen (welche Antwort triggert?)",
                "Prüfen, ob Daten/Compliance/Use-Case-Abgrenzung IPA möglich macht",
                "Falls nicht: RPA oder Prozess-/System-Redesign evaluieren",
            ],
        }
    elif ipa_score is not None:
        band = classify(ipa_score)
        result["ipa_recommendation"] = build_reco(dimension_code, 
                                                  dimension_name, "IPA", 
                                                  ipa_score, band["key"], 
                                                  band)
    else:
        result["ipa_recommendation"] = {
            "type": "info",
            "icon": "ℹ️",
            "color": "#3b82f6",
            "title": f"{dimension_name}: IPA nicht bewertet",
            "text": "Für IPA liegt in dieser Dimension kein Score "
            "vor (None). Prüfen Sie, ob die Dimension beantwortet/bewertet wurde.",
            "actions": ["Bewertungslogik prüfen (None vs. '-')", 
                        "Fehlende Antworten nachziehen", "Seed/Skala validieren"],
        }

    # 4) Optional: RPA vs IPA Priorisierung (genauere Unterscheidung)
    result["overall_recommendation"] = build_overall_preference(
        dimension_name=dimension_name,
        rpa_score=rpa_score, ipa_score=ipa_score,
        rpa_excluded=rpa_excluded, ipa_excluded=ipa_excluded
    )

    return result

# Helpers / Library
def default_actions_for_band(band_key, automation_type):
    """Fallback-Actions je Band, wenn kein spezifischer 
    Text/Actions im REC_LIBRARY definiert ist."""
    if band_key in ("critical", "high"):
        return [
            "Welche Antworten drücken den Score? Konkret benennen!",
            "Quick Fixes definieren (2–4 Wochen) + Owner festlegen",
            "Assessment erneut nach Umsetzung durchführen",
        ]
    if band_key == "medium":
        return [
            "Konkrete Verbesserungsmaßnahmen priorisieren (Top 3)",
            "Pilot/PoC mit klarer Definition of Done starten",
            "Messkriterien festlegen (Fehlerquote, Durchlaufzeit, Volumen)",
        ]
    if band_key == "good":
        return [
            "Pilotieren und dabei Standards/Guidelines dokumentieren",
            "Betrieb/Monitoring früh mitdenken (SLAs, Logging, Alerts)",
        ]
    return [
        "Skalierung planen (Roadmap, Pipeline, Governance)",
        "Best Practices als Template für weitere Use Cases nutzen",
    ]


def build_overall_preference(dimension_name, rpa_score, ipa_score, rpa_excluded, ipa_excluded):
    """
    Liefert eine einfache, aber hilfreiche Empfehlung zur Priorisierung.
    """
    # Wenn beide ausgeschlossen oder beide fehlen → keine Aussage
    if (rpa_excluded and ipa_excluded) or (rpa_score is None and ipa_score is None):
        return None

    # Wenn nur eine Option verfügbar ist
    if rpa_excluded or rpa_score is None:
        if not ipa_excluded and ipa_score is not None:
            return {
                "type": "info",
                "icon": "➡️",
                "color": "#3b82f6",
                "title": f"{dimension_name}: Fokus auf IPA",
                "text": f"RPA ist hier nicht verfügbar/bewertet. IPA ist die naheliegende Option (Score {ipa_score:.1f}/5).",
                "actions": ["IPA-PoC scopen", "Daten-/Modellanforderungen klären", "Risiken/Compliance prüfen"],
            }
        return None

    if ipa_excluded or ipa_score is None:
        return {
            "type": "info",
            "icon": "➡️",
            "color": "#3b82f6",
            "title": f"{dimension_name}: Fokus auf RPA",
            "text": f"IPA ist hier nicht verfügbar/bewertet. RPA ist die naheliegende Option (Score {rpa_score:.1f}/5).",
            "actions": ["RPA-PoC scopen", "Prozessstandardisierung "
            "sichern", "Betrieb/Monitoring planen"],
        }

    # Beide vorhanden → Vergleich
    diff = rpa_score - ipa_score
    if abs(diff) < 0.4:
        return {
            "type": "info",
            "icon": "⚖️",
            "color": "#3b82f6",
            "title": f"{dimension_name}: RPA und IPA ähnlich geeignet",
            "text": f"Die Eignung ist ähnlich (RPA {rpa_score:.1f}/5 vs. IPA {ipa_score:.1f}/5). Entscheide nach Nicht-Score-Kriterien (Zeit, Kosten, Risiko, Datenlage).",
            "actions": [
                "Entscheidungskriterien festlegen (Time-to-Value, Risiko, Wartung, Compliance)",
                "Mini-PoC für beide Ansätze (1–2 Wochen) vergleichen",
            ],
        }

    if diff >= 0.4:
        return {
            "type": "success",
            "icon": "🏁",
            "color": "#22c55e",
            "title": f"{dimension_name}: RPA bevorzugen",
            "text": f"RPA ist in dieser Dimension klar stärker (RPA {rpa_score:.1f}/5 vs. IPA {ipa_score:.1f}/5).",
            "actions": ["RPA priorisieren", "IPA optional als "
            "Ergänzung (z. B. Dokument-/Textanteile) prüfen"],
        }

    return {
        "type": "success",
        "icon": "🏁",
        "color": "#22c55e",
        "title": f"{dimension_name}: IPA bevorzugen",
        "text": f"IPA ist in dieser Dimension klar stärker (IPA {ipa_score:.1f}/5 vs. RPA {rpa_score:.1f}/5).",
        "actions": ["IPA priorisieren", "RPA optional als Orchestrierung/Backbone prüfen"],
    }


def build_recommendation_library():
    """
    Recommendation library pro Dimension und Band.
    Keys: dimension_code -> band_key -> {RPA/IPA oder generisch}
    """
    return {
        # Dimension 1: Plattformverfügbarkeit
        "1": {
            "critical": {
                "text": "Plattformverfügbarkeit ist kritisch (Score {score}/5). "
                "Ohne grundlegende Plattform-/Zugriffsfreigaben ist {automation_type} "
                "aktuell nicht sinnvoll.",
                "actions": [
                    "Stabilität & Verfügbarkeit messen (Uptime, Wartungsfenster, Releases)",
                    "Alternativen prüfen: APIs, Integration Layer, Systemanpassung",
                ],
            },
            "high": {
                "text": "Plattformverfügbarkeit ist instabil/unsicher (Score {score}/5). "
                "{automation_type} birgt hohes Betriebsrisiko (Ausfälle, UI-Änderungen,"
                "Zugriffsthemen).",
                "actions": [
                    "Technische Voraussetzungen in einem Checklist-Format fixieren",
                    "Change-/Release-Prozess der Plattform einbinden (Regression Tests)",
                    "Monitoring/Alerting für Automationsläufe definieren",
                ],
            },
            "medium": {
                "text": "Plattform ist grundsätzlich nutzbar, aber noch nicht "
                "robust genug (Score {score}/5). Für {automation_type} empfehlen sich "
                "Guardrails & Standardisierung.",
                "actions": [
                    "Stabile Schnittstellen priorisieren (API vor UI, wenn möglich)",
                    "Testfälle für UI-/Release-Änderungen definieren",
                    "Betriebskonzept (Runbook) vorbereiten",
                ],
            },
            "good": {
                "text": "Plattformverfügbarkeit ist solide (Score {score}/5). "
                "{automation_type} ist realistisch – Fokus auf saubere Umsetzung & Betrieb.",
            },
            "excellent": {
                "text": "Plattformverfügbarkeit ist sehr gut (Score {score}/5). "
                "Gute Basis, um {automation_type} zu skalieren.",
            },
            "_fallback_band": {"text": "Plattformverfügbarkeit (Score {score}/5): "
            "bitte Details prüfen."},
        },

        # Dimension 2: Organisatorisch
        "2": {
            "critical": {
                "text": "Kritische organisatorische Defizite (Score {score}/5). "
                "Ohne Ownership, Prozessverantwortung und Change-Plan scheitert "
                "{automation_type} häufig am Betrieb.",
                "actions": [
                    "Owner/Process Owner + RACI definieren",
                    "Change- & Kommunikationsplan (Betroffene, Trainings, Support) erstellen",
                    "Governance: Intake, Priorisierung, Release/Quality Gates festlegen",
                ],
            },
            "high": {
                "text": "Organisation ist noch nicht ausreichend vorbereitet "
                "(Score {score}/5). Für {automation_type} drohen Reibungsverluste "
                "(Akzeptanz, Betrieb, Verantwortlichkeiten).",
                "actions": [
                    "Stakeholder-Map + Sponsorship sichern",
                    "Supportmodell & Incident-Handling definieren",
                    "Dokumentationsstandard + Übergabeprozess etablieren",
                ],
            },
            "medium": {
                "text": "Organisatorische Basis ist vorhanden, aber ausbaufähig "
                "(Score {score}/5). {automation_type} sollte mit klaren Rollen & "
                "Standards pilotiert werden.",
                "actions": [
                    "Definition of Done + Abnahmekriterien vereinbaren",
                    "Betrieb/Monitoring/Ownership im Pilot verbindlich festlegen",
                    "Enablement: kurze Trainings + FAQ für Fachbereich",
                ],
            },
            "good": {"text": "Organisation ist gut aufgestellt (Score {score}/5). "
            "{automation_type} kann sauber pilotiert und in Betrieb überführt werden."},
            "excellent": {"text": "Organisation ist sehr reif (Score {score}/5)."
            " Gute Voraussetzungen für skalierbare {automation_type}-Rollouts."},
            "_fallback_band": {"text": "Organisatorik (Score {score}/5):"
            " bitte gezielt verbessern."},
        },

        # Dimension 3: Prozesseignung
        "3": {
            "critical": {
                "RPA": {
                    "text": "Prozess ist für RPA nicht geeignet (Score {score}/5): "
                    "zu viele Ausnahmen/Varianten, unklare Regeln oder instabile Inputs.",
                    "actions": [
                        "Prozessvarianten reduzieren (80/20) und Standardfall definieren",
                        "Regelwerk/Entscheidungslogik dokumentieren (wenn-dann)",
                        "Inputs standardisieren (Formulare, Pflichtfelder, Validierungen)",
                    ],
                },
                "IPA": {
                    "text": "Prozess ist für IPA kritisch (Score {score}/5): "
                    "Zieldefinition oder Qualitätskriterien fehlen.",
                    "actions": [
                        "Use Case präzisieren (Inputs/Outputs, Fehlerklassen, Guardrails)",
                        "Human-in-the-loop & Escalation-Logik definieren",
                    ],
                },
                "_fallback_type": {"text": "Prozess sehr kritisch (Score {score}/5)."},
            },
            "high": {
                "RPA": {
                    "text": "RPA-Eignung ist sehr schwach (Score {score}/5). "
                    "Fokus: Prozess stabilisieren, Ausnahmen minimieren, klare Regeln schaffen.",
                    "actions": [
                        "Ausnahmen kategorisieren (automatisierbar vs. manuell)",
                        "Prozessschritte vereinheitlichen & dokumentieren",
                        "Fehler-Quellen reduzieren",
                    ],
                },
                "IPA": {
                    "text": "IPA-Eignung ist schwach (Score {score}/5). Fokus: "
                    "Modellanforderungen konkretisieren, Qualität absichern.",
                    "actions": [
                        "Trainings-/Testdaten aufbauen",
                        "Versionierung etablieren und Qualitätskriterien definieren",
                    ],
                },
                "_fallback_type": {"text": "Prozess hoch riskant (Score {score}/5)."},
            },
            "medium": {
                "RPA": {
                    "text": "RPA-Eignung ist ausbaufähig (Score {score}/5). "
                    "Mit Standardisierung + klaren Regeln ist ein Pilot sinnvoll.",
                    "actions": [
                        "Standardfall priorisieren und zuerst automatisieren",
                        "Validierungen & Exception-Handling definieren",
                        "Prozessdoku + Testfälle aufbauen",
                    ],
                },
                "IPA": {
                    "text": "IPA-Eignung ist ausbaufähig (Score {score}/5). "
                    "Ein Pilot ist möglich, wenn Qualitätssicherung sauber stehen.",
                    "actions": [
                        "Fallback auf manuelle Prüfung definieren (Human-in-the-loop)",
                        "Sicherheits-/Compliance-Checks integrieren",
                    ],
                },
                "_fallback_type": {"text": "Prozess mittelmäßig (Score {score}/5)."},
            },
            "good": {
                "RPA": {"text": "Prozess ist gut RPA-geeignet (Score {score}/5). "
                "Fokus: Robustheit, Wartbarkeit, Monitoring."},
                "IPA": {"text": "Prozess ist gut IPA-geeignet (Score {score}/5). "
                "Fokus: Modellqualität, Governance, sichere Grenzen."},
                "_fallback_type": {"text": "Prozess solide (Score {score}/5)."},
            },
            "excellent": {
                "RPA": {"text": "Prozess ist sehr gut für RPA (Score {score}/5). "
                "Sehr gute Basis für Skalierung."},
                "IPA": {"text": "Prozess ist sehr gut für IPA (Score {score}/5). "
                "Sehr gute Basis für produktiven Einsatz."},
                "_fallback_type": {"text": "Prozess sehr gut (Score {score}/5)."},
            },
            "_fallback_band": {"text": "Prozesseignung (Score {score}/5): bitte verbessern."},
        },
        # Dimension 4: Daten
        "4": {
            "critical": {
                "RPA": {
                    "text": "Datenbasis ist kritisch für RPA (Score {score}/5): "
                    "Daten sind unvollständig, ungeeignet oder liegen nicht in "
                    "verarbeitbarer Form vor.",
                    "actions": [
                        "Datenquellen und Pflichtfelder klären "
                        "(Vollständigkeit/Verfügbarkeit sicherstellen)",
                        "Strukturierte Übergabe schaffen (z. B. Tabellen, "
                        "Formulare, standardisierte Exporte)",
                        "Bei OCR-/Freitextbedarf prüfen, ob Teilprozess für "
                        "RPA ungeeignet ist oder vorgelagert aufbereitet werden muss",
                    ],
                },
                "IPA": {
                    "text": "Datenbasis ist kritisch für IPA (Score {score}/5): "
                    "Datenqualität, Verfügbarkeit oder Eignung reichen für "
                    "robuste KI-gestützte Verarbeitung nicht aus.",
                    "actions": [
                        "Datenqualität und Datenabdeckung verbessern "
                        "(fehlende/inkonsistente Inhalte bereinigen)",
                        "Use Case eingrenzen und Trainings-/Referenzdaten für"
                        "Pilot gezielt aufbauen",
                        "OCR/NLP/Entscheidungslogik nur einsetzen, wenn Datenzugang, "
                        "Qualität und Validierung gesichert sind",
                    ],
                },
                "_fallback_type": {"text": "Datenbasis kritisch (Score {score}/5)."},
            },
            "high": {
                "RPA": {
                    "text": "Datenbasis ist schwach für RPA (Score {score}/5). Ohne "
                    "Standardisierung steigt Fehleranfälligkeit und Wartungsaufwand.",
                    "actions": [
                        "Eingabedaten standardisieren (Formatregeln, Pflichtfelder, Validierungen)",
                        "Ausnahmen und fehlende Angaben im Prozess explizit behandeln",
                        "Medienbrüche reduzieren (manuelle Übertragungen, Screenshots, Freitext) ",
                    ],
                },
                "IPA": {
                    "text": "Datenbasis ist anspruchsvoll für IPA (Score {score}/5). "
                    "Ohne Datenaufbereitung sinken Qualität und Verlässlichkeit der Ergebnisse.",
                    "actions": [
                        "Datenaufbereitung definieren (OCR-Qualität, Textbereinigung, "
                        "Klassifikationsregeln)",
                        "Menschliche Validierung für unsichere Ergebnisse einplanen",
                        "Pilotdaten mit realistischen Fällen und Grenzfällen aufbauen",
                    ],
                },
                "_fallback_type": {"text": "Datenbasis schwach (Score {score}/5)."},
            },
            "medium": {
                "RPA": {
                    "text": "Datenbasis ist gemischt (Score {score}/5). RPA ist "
                    "machbar, wenn Datenformate, Vollständigkeit und Ausnahmen "
                    "sauber geregelt werden."
                },
                "IPA": {
                    "text": "Datenbasis ist ausbaufähig (Score {score}/5). Ein "
                    "IPA-Pilot ist machbar, wenn OCR/Textverständnis und Validierung "
                    "gezielt abgesichert werden."
                },
                "_fallback_type": {"text": "Datenbasis mittel (Score {score}/5)."},
            },
            "good": {
                "text": "Datenbasis ist gut (Score {score}/5). Relevante "
                "Daten sind überwiegend verfügbar und geeignet; Fokus auf saubere "
                "Validierung und Betriebsfähigkeit."
            },
            "excellent": {
                "text": "Datenbasis ist sehr gut (Score {score}/5). "
                "Gute Voraussetzungen für stabile Automation und Skalierung."
            },
            "_fallback_band": {
                "text": "Datenbasis (Score {score}/5): bitte Datenverfügbarkeit, "
                "Qualität und Eignung prüfen."
            },
        },

        # Dimension 5: Technische Komplexität
        "5": {
            "critical": {
                "RPA": {
                    "text": "Technische Komplexität ist kritisch für RPA "
                    "(Score {score}/5): hohe UI-Volatilität, fehlende "
                    "Stabilität oder schwierige Integrationen.",
                    "actions": [
                        "API-/Integration-first prüfen (statt UI-Automation)",
                        "Systemzugriffe stabilisieren (Selectors, stabile IDs, Testumgebung)",
                        "Architekturentscheidung: RPA nur als Übergang oder gar nicht?",
                    ],
                },
                "IPA": {
                    "text": "Technische Komplexität ist kritisch für IPA "
                    "(Score {score}/5): fehlende Infrastruktur.",
                    "actions": [
                        "Security/Datenschutz/Hosting klären (Cloud vs. On-Prem)",
                        "Technische Machbarkeit im PoC validieren (Latency, Kosten, Qualität)",
                    ],
                },
                "_fallback_type": {"text": "Technik kritisch (Score {score}/5)."},
            },
            "high": {
                "RPA": {
                    "text": "RPA ist technisch riskant (Score {score}/5). "
                    "Ohne Stabilisierung sind Wartungskosten hoch.",
                    "actions": [
                        "Stabile Schnittstellen priorisieren",
                        "Regression-Tests automatisieren",
                    ],
                },
                "IPA": {
                    "text": "IPA ist technisch riskant (Score {score}/5). "
                    "Ohne Stabilisierung sind Wartungskosten hoch.",
                    "actions": [
                        "Rollout-Strategie (Canary, A/B) definieren",
                        "Rollen/Skills (Data/ML/Platform) sicherstellen",
                    ],
                },
                "_fallback_type": {"text": "Technik hoch riskant (Score {score}/5)."},
            },
            "medium": {
                "RPA": {"text": "Technische Komplexität ist erhöht (Score {score}/5). "
                "Mit Standards und Tests ist RPA machbar."},
                "IPA": {"text": "Technische Komplexität ist erhöht (Score {score}/5). "
                "Ein IPA-Pilot ist machbar."},
                "_fallback_type": {"text": "Technik mittel (Score {score}/5)."},
            },
            "good": {"text": "Technische Basis ist gut (Score {score}/5). "
            "Fokus auf saubere Implementierung & Betrieb."},
            "excellent": {"text": "Technische Basis ist sehr gut (Score {score}/5)."
            " Gute Voraussetzungen für Skalierung."},
            "_fallback_band": {"text": "Technik (Score {score}/5): bitte prüfen."},
        },

        # Dimension 6 Wirtschaftlichkeit
        "6": {
            "critical": {
                "text": "Wirtschaftlichkeit ist kritisch (Score {score}/5)."
                " Der Business Case trägt aktuell nicht (Volumen, Aufwand, Nutzen oder Risiko).",
                "actions": [
                    "ROI-Rechnung transparent machen (Setup + Run + Change-Kosten)",
                    "Volumen/Automationsquote erhöhen oder Scope reduzieren",
                    "Alternative: Prozess-/Systemverbesserung statt Automation prüfen",
                ],
            },
            "high": {
                "text": "Wirtschaftlichkeit ist schwach (Score {score}/5). "
                "Ohne Anpassung droht niedriger ROI.",
                "actions": [
                    "Quick-Wins identifizieren (hohes Volumen, klare Regeln)",
                    "Setup-Aufwand reduzieren (Templates, Reuse, Standardkomponenten)",
                    "Benefit Tracking definieren (Zeit, Qualität, Compliance)",
                ],
            },
            "medium": {
                "text": "Wirtschaftlichkeit ist ausbaufähig (Score {score}/5). "
                "Mit sauberem Scope und Skalierung kann sich {automation_type} lohnen.",
                "actions": [
                    "Pilot mit messbaren KPIs (Zeitersparnis, Fehlerquote) durchführen",
                    "Skalierungshebel identifizieren (mehr Fälle, mehr Länder, mehr Teams)",
                    "Betriebskosten früh berücksichtigen (Monitoring, Support, Changes)",
                ],
            },
            "good": {"text": "Wirtschaftlichkeit ist solide (Score {score}/5). "
            "Fokus: Pilot → Skalierung mit sauberem KPI-Tracking."},
            "excellent": {"text": "Wirtschaftlichkeit ist sehr gut (Score {score}/5). "
            "Gute Basis für schnelle Skalierung."},
            "_fallback_band": {"text": "Wirtschaftlichkeit (Score {score}/5): bitte verbessern."},
        },

        # Fallback für unbekannte Dimensionen
        "_fallback": {
            "_fallback_band": {"text": "Dimension (Score {score}/5): bitte prüfen."},
        }
    }
# Route: Assessment aktualisieren
@app.route('/assessment/<int:assessment_id>/update', methods=['POST'])
def update_assessment(assessment_id):
    """Aktualisiert ein existierendes Assessment"""
    try:
        assessment = Assessment.query.get_or_404(assessment_id)
        process = db.session.get(Process, assessment.process_id)
        qv = db.session.get(QuestionnaireVersion, assessment.questionnaire_version_id)

        # 1. Aktualisiere Process
        process.name = request.form.get('uc_name', process.name)
        process.description = request.form.get('uc_desc', process.description)
        process.industry = request.form.get('industry', process.industry)

        # 2. Lösche alte Antworten
        Answer.query.filter_by(assessment_id=assessment_id).delete()

        # 3. Speichere neue Antworten
        all_questions = Question.query.filter_by(
            questionnaire_version_id=qv.id
        ).all()

        for question in all_questions:
            field_single = f"q_{question.id}"
            field_multi = f"q_{question.id}[]"

            if question.question_type == "single_choice":
                value = request.form.get(field_single)
                answer = Answer(
                    assessment_id=assessment.id,
                    question_id=question.id,
                    scale_option_id=int(value) if value else None,
                    is_applicable=True
                )
                db.session.add(answer)

            elif question.question_type == "multiple_choice":
                values = request.form.getlist(field_multi)
                if values:
                    for v in values:
                        answer = Answer(
                            assessment_id=assessment.id,
                            question_id=question.id,
                            scale_option_id=int(v),
                            is_applicable=True
                        )
                        db.session.add(answer)
                else:
                    answer = Answer(
                        assessment_id=assessment.id,
                        question_id=question.id,
                        scale_option_id=None,
                        is_applicable=True
                    )
                    db.session.add(answer)

            elif question.question_type == "number":
                value = request.form.get(field_single)
                if value and value.strip():
                    try:
                        num = float(value.replace(',', '.'))
                        answer = Answer(
                            assessment_id=assessment.id,
                            question_id=question.id,
                            numeric_value=num,
                            is_applicable=True
                        )
                    except ValueError:
                        answer = Answer(
                            assessment_id=assessment.id,
                            question_id=question.id,
                            numeric_value=None,
                            is_applicable=True
                        )
                else:
                    answer = Answer(
                        assessment_id=assessment.id,
                        question_id=question.id,
                        numeric_value=None,
                        is_applicable=True
                    )
                db.session.add(answer)

        db.session.commit()

        # 3.5. Speichere gemeinsame Antworten für Dimensionen 1 & 2 wenn aktiviert
        use_shared_dims = request.form.get('use_shared_dimensions') == 'on'
        if use_shared_dims:
            shared_dim_ids = get_shared_dimension_ids()

            for dim_id in shared_dim_ids:
                # Sammle alle Antworten für diese Dimension
                dim_questions = Question.query.filter_by(dimension_id=dim_id).all()
                dim_answers = {}

                for q in dim_questions:
                    field_single = f"q_{q.id}"
                    field_multi = f"q_{q.id}[]"

                    if q.question_type == "number":
                        value = request.form.get(field_single)
                        if value and value.strip():
                            try:
                                dim_answers[q.id] = {'numeric': float(value.replace(',', '.')),
                                                     'single': None, 'multi': []}
                            except ValueError:
                                pass
                    elif q.question_type == "single_choice":
                        value = request.form.get(field_single)
                        if value:
                            dim_answers[q.id] = {'numeric': None, 'single': int(value), 'multi': []}
                    elif q.question_type == "multiple_choice":
                        values = request.form.getlist(field_multi)
                        if values:
                            dim_answers[q.id] = {'numeric': None, 'single': None,
                                                 'multi': [int(v) for v in values]}
                if dim_answers:
                    save_shared_dimension_answers(dim_id, dim_answers)

            db.session.commit()

        # 4. Filterlogik anwenden
        apply_filter_logic(assessment_id)
        db.session.commit()

        # 5. Lösche alte Ergebnisse
        DimensionResult.query.filter_by(assessment_id=assessment_id).delete()
        TotalResult.query.filter_by(assessment_id=assessment_id).delete()
        db.session.commit()

        # 6. Berechne neue Ergebnisse
        total_result = ScoringService.calculate_assessment_results(assessment.id)

        return redirect(url_for('view_assessment', assessment_id=assessment_id))

    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return f"Fehler: {str(e)}", 500

# Route: Bewertung auswerten
@app.route('/evaluate', methods=['POST'])
def evaluate():
    """Verarbeitet die eingereichten Antworten, speichert sie in der Datenbank, 
    wendet die Filterlogik an und berechnet die Ergebnisse.
    """

    try:
        # 1. Erstelle Prozess
        process = Process(
            name=request.form.get('uc_name', 'Unbekannter Prozess'),
            description=request.form.get('uc_desc', ''),
            industry=request.form.get('industry', '')
        )
        db.session.add(process)
        db.session.flush()

        # 2. Erstelle Assessment
        qv = QuestionnaireVersion.query.filter_by(is_active=True).first()
        if not qv:
            return "Keine aktive Fragebogen-Version gefunden", 500
        assessment = Assessment(
            process_id=process.id,
            questionnaire_version_id=qv.id
        )
        db.session.add(assessment)
        db.session.flush()
        # 3. Hole ALLE Fragen
        all_questions = Question.query.filter_by(
            questionnaire_version_id=qv.id
        ).all()

        # 4. Speichere Antworten
        answered_count = 0
        unanswered_count = 0

        for question in all_questions:
            field_single = f"q_{question.id}"
            field_multi = f"q_{question.id}[]"

            if question.question_type == "single_choice":
                value = request.form.get(field_single)

                answer = Answer(
                    assessment_id=assessment.id,
                    question_id=question.id,
                    scale_option_id=int(value) if value else None,
                    is_applicable=True
                )
                db.session.add(answer)

                if value:
                    answered_count += 1
                else:
                    unanswered_count += 1

            elif question.question_type == "multiple_choice":
                values = request.form.getlist(field_multi)

                if values:
                    for v in values:
                        answer = Answer(
                            assessment_id=assessment.id,
                            question_id=question.id,
                            scale_option_id=int(v),
                            is_applicable=True
                        )
                        db.session.add(answer)
                    answered_count += 1
                else:
                    answer = Answer(
                        assessment_id=assessment.id,
                        question_id=question.id,
                        scale_option_id=None,
                        is_applicable=True
                    )
                    db.session.add(answer)
                    unanswered_count += 1

            elif question.question_type == "number":
                value = request.form.get(field_single)

                if value and value.strip():
                    try:
                        num = float(value.replace(',', '.'))
                        answer = Answer(
                            assessment_id=assessment.id,
                            question_id=question.id,
                            numeric_value=num,
                            is_applicable=True
                        )
                        answered_count += 1
                    except ValueError:
                        answer = Answer(
                            assessment_id=assessment.id,
                            question_id=question.id,
                            numeric_value=None,
                            is_applicable=True
                        )
                        unanswered_count += 1
                else:
                    answer = Answer(
                        assessment_id=assessment.id,
                        question_id=question.id,
                        numeric_value=None,
                        is_applicable=True
                    )
                    unanswered_count += 1

                db.session.add(answer)

        db.session.commit()

        # Speichere gemeinsame Antworten für Dimensionen 1 & 2 wenn aktiviert
        use_shared_dims = request.form.get('use_shared_dimensions') == 'on'
        if use_shared_dims:
            shared_dim_ids = get_shared_dimension_ids()

            for dim_id in shared_dim_ids:
                # Sammle alle Antworten für diese Dimension
                dim_questions = Question.query.filter_by(dimension_id=dim_id).all()
                dim_answers = {}
                for q in dim_questions:
                    field_single = f"q_{q.id}"
                    field_multi = f"q_{q.id}[]"
                    if q.question_type == "number":
                        value = request.form.get(field_single)
                        if value and value.strip():
                            try:
                                dim_answers[q.id] = {'numeric': float(value.replace(',', '.')),
                                                     'single': None, 'multi': []}
                            except ValueError:
                                pass
                    elif q.question_type == "single_choice":
                        value = request.form.get(field_single)
                        if value:
                            dim_answers[q.id] = {'numeric': None, 'single': int(value), 'multi': []}
                    elif q.question_type == "multiple_choice":
                        values = request.form.getlist(field_multi)
                        if values:
                            dim_answers[q.id] = {'numeric': None, 'single': None,
                                                 'multi': [int(v) for v in values]}

                if dim_answers:
                    save_shared_dimension_answers(dim_id, dim_answers)

            db.session.commit()

        # 5. Filterlogik anwenden
        apply_filter_logic(assessment.id)
        db.session.commit()

        total_result = ScoringService.calculate_assessment_results(assessment.id)

        # 7. Redirect zur Ergebnisseite
        return redirect(url_for('view_assessment', assessment_id=assessment.id))
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return f"Fehler: {str(e)}", 500

# Route: Vergleichsübersicht
@app.route('/comparison')
def comparison():
    """Zeigt alle gespeicherten Assessments zum Vergleich"""
    results = db.session.query(
        TotalResult, Assessment, Process
    ).join(
        Assessment, TotalResult.assessment_id == Assessment.id
    ).join(
        Process, Assessment.process_id == Process.id
    ).all()
    assessments_data = []
    for total_result, assessment, process in results:
        if total_result.total_rpa and total_result.total_ipa:
            combined_score = max(total_result.total_rpa, total_result.total_ipa)
        elif total_result.total_rpa:
            combined_score = total_result.total_rpa
        elif total_result.total_ipa:
            combined_score = total_result.total_ipa
        else:
            combined_score = 0

        assessments_data.append({
            'id': assessment.id,
            'process_name': process.name,
            'industry': process.industry,
            'created_at': assessment.created_at,
            'total_rpa': total_result.total_rpa,
            'total_ipa': total_result.total_ipa,
            'rpa_excluded': total_result.rpa_excluded,
            'ipa_excluded': total_result.ipa_excluded,
            'combined_score': combined_score
        })
    return render_template('comparison.html', assessments=assessments_data)

# Route: Assessment anzeigen
@app.route('/assessment/<int:assessment_id>')
def view_assessment(assessment_id):
    """Zeigt Ergebnisse eines Assessments"""

    assessment = Assessment.query.get_or_404(assessment_id)
    process = db.session.get(Process, assessment.process_id)

    # Gesamtergebnis
    total_result = TotalResult.query.filter_by(assessment_id=assessment_id).first()

    # Dimensionsergebnisse
    dim_results = db.session.query(
        DimensionResult, Dimension
    ).join(
        Dimension, DimensionResult.dimension_id == Dimension.id
    ).filter(
        DimensionResult.assessment_id == assessment_id
    ).order_by(
        Dimension.sort_order, DimensionResult.automation_type
    ).all()
    # Gruppiere Ergebnisse nach Dimension (pro Dimension gibt es RPA und IPA)
    dimensions_by_id = {}
    for dim_result, dimension in dim_results:
        if dimension.id not in dimensions_by_id:
            dimensions_by_id[dimension.id] = {
                'code': dimension.code,
                'name': dimension.name,
                'calc_method': dimension.calc_method,
                'is_shared': dimension.code in ['1', '7'],
                'rpa_score': None,
                'ipa_score': None,
                'rpa_excluded': False,
                'ipa_excluded': False,
                'answers': []
            }
        # Speichere Score basierend auf automation_type
        if dim_result.automation_type == "RPA":
            dimensions_by_id[dimension.id]['rpa_score'] = dim_result.mean_score
            dimensions_by_id[dimension.id]['rpa_excluded'] = dim_result.is_excluded
        elif dim_result.automation_type == "IPA":
            dimensions_by_id[dimension.id]['ipa_score'] = dim_result.mean_score
            dimensions_by_id[dimension.id]['ipa_excluded'] = dim_result.is_excluded
    # Lade Antworten für jede Dimension
    from models.database import Question, Answer, ScaleOption, OptionScore

    for dimension_id, dim_data in dimensions_by_id.items():
        # Hole alle Fragen für diese Dimension
        questions = Question.query.filter_by(dimension_id=
                                             dimension_id).order_by(Question.
                                                                    sort_order).all()

        for question in questions:
            # Hole ALLE Antworten für diese Frage (wichtig für Multiple Choice)
            answers = Answer.query.filter_by(
                assessment_id=assessment_id,
                question_id=question.id
            ).all()

            if not answers:
                continue

            # Formatiere Antwort(en)
            answer_text = "Keine Antwort"
            all_option_ids = []

            if question.question_type == "number":
                # Numerische Frage - nur eine Antwort
                if answers[0].numeric_value is not None:
                    answer_text = f"{answers[0].numeric_value}"
                    if question.unit:
                        answer_text += f" {question.unit}"

            elif question.question_type == "multiple_choice":
                # Multiple Choice - mehrere Antworten möglich
                selected_options = []
                for ans in answers:
                    if ans.scale_option_id:
                        option = db.session.get(ScaleOption, ans.scale_option_id)
                        if option:
                            selected_options.append(option.label)
                            all_option_ids.append(ans.scale_option_id)

                if selected_options:
                    answer_text = ", ".join(selected_options)

            else:
                # Single Choice - nur eine Antwort
                if answers[0].scale_option_id:
                    option = db.session.get(ScaleOption, answers[0].scale_option_id)
                    if option:
                        answer_text = option.label
                        all_option_ids.append(answers[0].scale_option_id)

            # Hole Scores für diese Antwort(en)
            rpa_score_text = "–"
            ipa_score_text = "–"

            if all_option_ids:
                # Für Multiple Choice: Zeige den höchsten Score an
                if question.question_type == "multiple_choice":
                    # Hole alle OptionScores für die gewählten Optionen
                    rpa_scores_objs = OptionScore.query.filter(
                        OptionScore.question_id == question.id,
                        OptionScore.scale_option_id.in_(all_option_ids),
                        OptionScore.automation_type == "RPA"
                    ).all()

                    ipa_scores_objs = OptionScore.query.filter(
                        OptionScore.question_id == question.id,
                        OptionScore.scale_option_id.in_(all_option_ids),
                        OptionScore.automation_type == "IPA"
                    ).all()

                    # RPA: Prüfe auf Ausschluss, dann höchster Score
                    if any(s.is_exclusion for s in rpa_scores_objs):
                        rpa_score_text = "AUSSCHLUSS"
                    else:
                        applicable_rpa = [s.score for s in rpa_scores_objs if
                                          s.is_applicable and s.score is not None]
                        if applicable_rpa:
                            rpa_score_text = f"{max(applicable_rpa):.1f} (max)"

                    # IPA: Prüfe auf Ausschluss, dann höchster Score
                    if any(s.is_exclusion for s in ipa_scores_objs):
                        ipa_score_text = "AUSSCHLUSS"
                    else:
                        applicable_ipa = [s.score for s in ipa_scores_objs if
                                          s.is_applicable and s.score is not None]
                        if applicable_ipa:
                            ipa_score_text = f"{max(applicable_ipa):.1f} (max)"

                else:
                    # Single Choice
                    option_id = all_option_ids[0]

                    # RPA Score
                    rpa_score_obj = OptionScore.query.filter_by(
                        question_id=question.id,
                        scale_option_id=option_id,
                        automation_type="RPA"
                    ).first()

                    if rpa_score_obj:
                        if rpa_score_obj.is_exclusion:
                            rpa_score_text = "AUSSCHLUSS"
                        elif not rpa_score_obj.is_applicable:
                            rpa_score_text = "N/A"
                        elif rpa_score_obj.score is not None:
                            rpa_score_text = f"{rpa_score_obj.score:.1f}"

                    # IPA Score
                    ipa_score_obj = OptionScore.query.filter_by(
                        question_id=question.id,
                        scale_option_id=option_id,
                        automation_type="IPA"
                    ).first()

                    if ipa_score_obj:
                        if ipa_score_obj.is_exclusion:
                            ipa_score_text = "AUSSCHLUSS"
                        elif not ipa_score_obj.is_applicable:
                            ipa_score_text = "N/A"
                        elif ipa_score_obj.score is not None:
                            ipa_score_text = f"{ipa_score_obj.score:.1f}"

            dim_data['answers'].append({
                'question_code': question.code,
                'question_text': question.text,
                'answer': answer_text,
                'is_applicable': answers[0].is_applicable,
                'rpa_score': rpa_score_text,
                'ipa_score': ipa_score_text
            })

    # Formatiere Dimensionsergebnisse (sortiert nach Sort-Order)
    dimensions_data = []
    for dim_result, dimension in dim_results:
        if dimension.id in dimensions_by_id:
            data = dimensions_by_id.pop(dimension.id)
            dimensions_data.append(data)
    for dim_data in dimensions_data:
        recommendations = generate_dimension_recommendations(
            dimension_code=dim_data['code'],
            dimension_name=dim_data['name'],
            rpa_score=dim_data['rpa_score'],
            ipa_score=dim_data['ipa_score'],
            rpa_excluded=dim_data['rpa_excluded'],
            ipa_excluded=dim_data['ipa_excluded']
        )
        # Füge Empfehlungen zu den Dimensionsdaten hinzu
        dim_data['rpa_recommendation'] = recommendations['rpa_recommendation']
        dim_data['ipa_recommendation'] = recommendations['ipa_recommendation']
    # Berechne max_score basierend auf Anzahl der Dimensionen
    num_dimensions = len(dimensions_data)
    max_score = num_dimensions * 5.0
    # Extrahiere Gesamtscores
    total_rpa = total_result.total_rpa if total_result else None
    total_ipa = total_result.total_ipa if total_result else None
    rpa_excluded = total_result.rpa_excluded if total_result else False
    ipa_excluded = total_result.ipa_excluded if total_result else False

    # Lade Economic Metrics
    economic_metrics_data = {}
    econ_metrics = EconomicMetric.query.filter_by(assessment_id=assessment_id).all()
    for metric in econ_metrics:
        economic_metrics_data[metric.key] = {
            'value': metric.value,
            'unit': metric.unit
        }

    return render_template(
        'result.html',
        use_case=process,
        assessment=assessment,
        assessment_id=assessment_id,
        total_result=total_result,
        total_rpa=total_rpa,  # Für Template-Zugriff
        total_ipa=total_ipa,  # Für Template-Zugriff
        rpa_excluded=rpa_excluded,  # Für Template-Zugriff
        ipa_excluded=ipa_excluded,  # Für Template-Zugriff
        max_score=max_score,  # Für Balkendiagramme
        dimensions=dimensions_data,
        breakdown=dimensions_data,  # Für Dimensionsdetails-Dropdown
        economic_metrics=economic_metrics_data if economic_metrics_data else None,
        run_id=assessment_id,
        recommendation=total_result.recommendation if total_result else None,
    )

# Route: Assessment löschen
@app.route('/assessment/<int:assessment_id>/delete', methods=['POST'])
def delete_assessment(assessment_id):
    """Löscht ein Assessment und alle zugehörigen Daten"""
    try:
        assessment = Assessment.query.get_or_404(assessment_id)
        process_id = assessment.process_id
        # 1. Lösche Antworten
        Answer.query.filter_by(assessment_id=assessment_id).delete()

        # 2. Lösche Dimensionsergebnisse
        DimensionResult.query.filter_by(assessment_id=assessment_id).delete()

        # 3. Lösche Gesamtergebnis
        TotalResult.query.filter_by(assessment_id=assessment_id).delete()

        # 4. Lösche Economic Metrics
        EconomicMetric.query.filter_by(assessment_id=assessment_id).delete()

        # 5. Lösche Assessment selbst
        db.session.delete(assessment)

        # 6. Prüfe ob Process noch weitere Assessments hat
        db.session.flush()  # Stelle sicher dass das Assessment gelöscht ist
        remaining = Assessment.query.filter_by(process_id=process_id).count()

        if remaining == 0:
            # Lösche Process wenn keine weiteren Assessments vorhanden
            process = db.session.get(Process, process_id)
            if process:
                db.session.delete(process)

        db.session.commit()

        # Redirect mit Erfolgsmeldung
        return redirect(url_for('comparison', deleted='true'))

    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return f"Fehler beim Löschen: {str(e)}", 500

# Route: Gemeinsame Dimensionen zurücksetzen
@app.route('/reset_shared_dimensions', methods=['POST'])
def reset_shared_dimensions():
    """Löscht alle gemeinsam gespeicherten Dimensionsantworten"""

    try:
        shared_dim_ids = get_shared_dimension_ids()

        for dim_id in shared_dim_ids:
            SharedDimensionAnswer.query.filter_by(dimension_id=dim_id).delete()

        db.session.commit()
        return jsonify({'success': True}), 200 
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# Route: CSV Export
@app.route('/assessment/<int:assessment_id>/export')
def export_assessment(assessment_id):
    """Exportiert Assessment als CSV"""
    assessment = Assessment.query.get_or_404(assessment_id)
    process = db.session.get(Process, assessment.process_id)
    total_result = TotalResult.query.filter_by(assessment_id=assessment_id).first()
    dim_results = db.session.query(
        DimensionResult, Dimension
    ).join(
        Dimension, DimensionResult.dimension_id == Dimension.id
    ).filter(
        DimensionResult.assessment_id == assessment_id
    ).order_by(
        Dimension.sort_order
    ).all()
    # CSV erstellen
    output = StringIO()
    writer = csv.writer(output)
    # Header
    writer.writerow(['Assessment Export'])
    writer.writerow(['Prozess', process.name])
    writer.writerow(['Branche', process.industry or '-'])
    writer.writerow(['Beschreibung', process.description or '-'])
    writer.writerow([])
    # Gesamtergebnis
    writer.writerow(['Gesamtergebnis'])
    writer.writerow(['Typ', 'Score', 'Status'])
    writer.writerow(['RPA', total_result.total_rpa or '-',
                     'Ausgeschlossen' if total_result.rpa_excluded else 'Bewertet'])
    writer.writerow(['IPA', total_result.total_ipa or '-',
                     'Ausgeschlossen' if total_result.ipa_excluded else 'Bewertet'])
    writer.writerow([])
    # Dimensionsergebnisse
    writer.writerow(['Dimensionsergebnisse'])
    writer.writerow(['Code', 'Dimension', 'RPA Score', 'IPA Score'])
    # Gruppiere Dimensionsergebnisse nach Dimension
    dims_by_id = {}
    for dim_result, dimension in dim_results:
        if dimension.id not in dims_by_id:
            dims_by_id[dimension.id] = {
                'code': dimension.code,
                'name': dimension.name,
                'rpa': None,
                'ipa': None
            }
        if dim_result.automation_type == 'RPA':
            dims_by_id[dimension.id]['rpa'] = dim_result.mean_score
        elif dim_result.automation_type == 'IPA':
            dims_by_id[dimension.id]['ipa'] = dim_result.mean_score
    # Schreibe Zeilen
    for dim_id, dim_data in dims_by_id.items():
        writer.writerow([
            dim_data['code'],
            dim_data['name'],
            dim_data['rpa'] if dim_data['rpa'] is not None else '-',
            dim_data['ipa'] if dim_data['ipa'] is not None else '-'
        ])
    # Response
    output.seek(0)
    return Response(
        output,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=assessment_{assessment_id}.csv'}
    )


# Main
if __name__ == '__main__':
    init_database()
    app.run(debug=True, host='0.0.0.0', port=5000)
