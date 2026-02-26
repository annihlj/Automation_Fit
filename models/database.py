"""
Datenbankmodelle
"""
from datetime import datetime
from extensions import db

# Masterdaten

class QuestionnaireVersion(db.Model):
    """Versionierte Definition eines Fragebogens mit zugehörigen Fragen und Dimensionen."""
    __tablename__ = "questionnaire_version"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    version = db.Column(db.String(50), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Bezeihungen
    dimensions = db.relationship('Dimension', backref='questionnaire_version', lazy=True)
    questions = db.relationship('Question', backref='questionnaire_version', lazy=True)


class Dimension(db.Model):
    """Thematischer Bewertungsbereich innerhalb einer Fragebogenversion."""
    __tablename__ = "dimension"
    id = db.Column(db.Integer, primary_key=True)
    questionnaire_version_id = db.Column(db.Integer,
                                         db.ForeignKey("questionnaire_version.id"),
                                           nullable=False)
    code = db.Column(db.String(10), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    calc_method = db.Column(db.String(30), nullable=False, default="mean")

    # Beziehungen
    questions = db.relationship('Question', backref='dimension', lazy=True)


class Scale(db.Model):
    """Skala zur Bewertung von Fragen"""
    __tablename__ = "scale"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    label = db.Column(db.String(120), nullable=False)

    # Beziehungen
    options = db.relationship('ScaleOption', backref='scale', lazy=True)


class ScaleOption(db.Model):
    """Option innerhalb einer Skala zur Bewertung von Fragen"""
    __tablename__ = "scale_option"
    id = db.Column(db.Integer, primary_key=True)
    scale_id = db.Column(db.Integer, db.ForeignKey("scale.id"), nullable=False)
    code = db.Column(db.String(20), nullable=False)
    label = db.Column(db.String(255), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_na = db.Column(db.Boolean, default=False)

    __table_args__ = (
        db.UniqueConstraint("scale_id", "code", name="uq_scale_option"),
    )

class QuestionCondition(db.Model):
    """Bedingung, wann eine Frage basierend auf einer
    anderen Antwort sichtbar ist. Dynamischer Verlauf"""
    __tablename__ = "question_condition"
    id = db.Column(db.Integer, primary_key=True)

    # Die abhängige Frage
    question_id = db.Column(db.Integer, db.ForeignKey("question.id"), nullable=False)

    # Parent-Frage
    depends_on_question_id = db.Column(db.Integer, db.ForeignKey("question.id"), nullable=False)

    # Option, die gewählt sein muss
    depends_on_option_id = db.Column(db.Integer, db.ForeignKey("scale_option.id"), nullable=False)

    sort_order = db.Column(db.Integer, default=0)

class Question(db.Model):
    """Frageelement eines Fragebogens inkl. Typ, Skala und optionaler Filterlogik."""
    __tablename__ = "question"
    id = db.Column(db.Integer, primary_key=True)
    questionnaire_version_id = db.Column(db.Integer,
                                         db.ForeignKey("questionnaire_version.id"), nullable=False)
    dimension_id = db.Column(db.Integer, db.ForeignKey("dimension.id"), nullable=False)
    code = db.Column(db.String(20), nullable=False)
    text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(20), nullable=False)
    unit = db.Column(db.String(20), nullable=True)
    scale_id = db.Column(db.Integer, db.ForeignKey("scale.id"), nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    # Felder für Filterlogik
    is_filter_question = db.Column(db.Boolean, default=False)
    depends_on_question_id = db.Column(db.Integer, db.ForeignKey("question.id"), nullable=True)
    depends_on_option_id = db.Column(db.Integer, db.ForeignKey("scale_option.id"), nullable=True)
    filter_description = db.Column(db.Text, nullable=True)
    depends_logic = db.Column(db.String(10), default="all", nullable=False)
    __table_args__ = (
        db.UniqueConstraint("questionnaire_version_id", "code", name="uq_question_code"),
    )

    # Beziehungen
    scale = db.relationship('Scale', backref='questions')
    option_scores = db.relationship('OptionScore', backref='question', lazy=True)
    dependent_questions = db.relationship('Question',
                                          backref=db.backref('parent_question', remote_side=[id]),
                                          foreign_keys=[depends_on_question_id])
    conditions = db.relationship(
        "QuestionCondition",
        foreign_keys=[QuestionCondition.question_id],
        backref="question",
        cascade="all, delete-orphan"
    )

class OptionScore(db.Model):
    """Bewertungszuordnung einer Antwortoption zu einem Automatisierungstyp."""
    __tablename__ = "option_score"
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("question.id"), nullable=False)
    scale_option_id = db.Column(db.Integer, db.ForeignKey("scale_option.id"), nullable=False)
    automation_type = db.Column(db.String(10), nullable=False)
    score = db.Column(db.Float, nullable=True)
    is_exclusion = db.Column(db.Boolean, default=False)
    is_applicable = db.Column(db.Boolean, default=True)

    __table_args__ = (
        db.UniqueConstraint("question_id", "scale_option_id",
                            "automation_type", name="uq_option_score"),
    )

    # Beziehungen
    scale_option = db.relationship('ScaleOption', backref='scores')

# AUSFÜLLUNG & ANTWORTEN

class Process(db.Model):
    """Bewerteter Prozess mit Metadaten und Verknüpfung zu Assessments."""
    __tablename__ = "process"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    industry = db.Column(db.String(80))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Beziehungen
    assessments = db.relationship('Assessment', backref='process', lazy=True)


class Assessment(db.Model):
    """Konkrete Bewertung eines Prozesses mit Verknüpfung zu Fragen, Antworten und Ergebnissen."""
    __tablename__ = "assessment"
    id = db.Column(db.Integer, primary_key=True)
    process_id = db.Column(db.Integer, db.ForeignKey("process.id"), nullable=False)
    questionnaire_version_id = db.Column(db.Integer,
                                         db.ForeignKey("questionnaire_version.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Beziehungen
    answers = db.relationship('Answer', backref='assessment', lazy=True)
    dimension_results = db.relationship('DimensionResult', backref='assessment', lazy=True)


class Answer(db.Model):
    """Antworten auf Fragen innerhalb eines Assessments, inklusive Bewertung und Anwendbarkeit.
    """
    __tablename__ = "answer"
    id = db.Column(db.Integer, primary_key=True)
    assessment_id = db.Column(db.Integer, db.ForeignKey("assessment.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("question.id"), nullable=False)
    scale_option_id = db.Column(db.Integer, db.ForeignKey("scale_option.id"), nullable=True)
    numeric_value = db.Column(db.Float, nullable=True)

    is_applicable = db.Column(db.Boolean, default=True, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("assessment_id", "question_id", "scale_option_id",
                          name="uq_answer_assessment_question_option"),
    )

    # Beziehungen
    question_obj = db.relationship('Question', backref='answers')
    scale_option = db.relationship('ScaleOption', backref='answers')

# ERGEBNISSE
class DimensionResult(db.Model):
    """Ergebnis einer Dimension innerhalb eines Assessments, 
    inklusive Durchschnittswert und Ausschlussinformationen."""
    __tablename__ = "dimension_result"
    id = db.Column(db.Integer, primary_key=True)
    assessment_id = db.Column(db.Integer, db.ForeignKey("assessment.id"), nullable=False)
    dimension_id = db.Column(db.Integer, db.ForeignKey("dimension.id"), nullable=False)
    automation_type = db.Column(db.String(10), nullable=False)
    mean_score = db.Column(db.Float, nullable=True)
    is_excluded = db.Column(db.Boolean, default=False)
    excluded_by_question_id = db.Column(db.Integer, db.ForeignKey("question.id"), nullable=True)

    __table_args__ = (
        db.UniqueConstraint("assessment_id", "dimension_id",
                            "automation_type", name="uq_dim_result"),
    )

    # Beziehungen
    dimension_obj = db.relationship('Dimension', backref='results')


class TotalResult(db.Model):
    """Gesamtergebnis eines Assessments mit Gesamtbewertung, 
    Ausschlussinformationen und Empfehlungen."""
    __tablename__ = "total_result"
    id = db.Column(db.Integer, primary_key=True)
    assessment_id = db.Column(db.Integer,
                              db.ForeignKey("assessment.id"),
                              nullable=False, unique=True)
    total_rpa = db.Column(db.Float, nullable=True)
    total_ipa = db.Column(db.Float, nullable=True)
    rpa_excluded = db.Column(db.Boolean, default=False)
    ipa_excluded = db.Column(db.Boolean, default=False)
    recommendation = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Beziehungen
    assessment_obj = db.relationship('Assessment', backref='total_result', uselist=False)


class EconomicMetric(db.Model):
    """Wirtschaftliche Kennzahl zur Quantifizierung von 
    Automatisierungspotenzialen, Kosten oder Einsparungen."""
    __tablename__ = "economic_metric"
    id = db.Column(db.Integer, primary_key=True)
    assessment_id = db.Column(db.Integer, db.ForeignKey("assessment.id"), nullable=False)
    automation_type = db.Column(db.String(10), nullable=True)
    key = db.Column(db.String(50), nullable=False)
    value = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20), nullable=True)

    # Beziehungen
    assessment_obj = db.relationship('Assessment', backref='economic_metrics')


class Hint(db.Model):
    """Hinweise für bestimmte Antworten"""
    __tablename__ = "hint"
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("question.id"), nullable=False)
    scale_option_id = db.Column(db.Integer, db.ForeignKey("scale_option.id"), nullable=True)
    automation_type = db.Column(db.String(10), nullable=True)  # RPA/IPA/NULL (für beide)
    hint_text = db.Column(db.Text, nullable=False)
    hint_type = db.Column(db.String(20), default="info")  # info, warning, error
    # Beziehungen
    question_obj = db.relationship('Question', backref='hints')
    scale_option = db.relationship('ScaleOption', backref='hints')


class SharedDimensionAnswer(db.Model):
    """
    Gemeinsame Antworten für Dimensionen (Plattform & Organisation)
    Diese Antworten werden dimensional gespeichert und bei neuen Assessments 
    automatisch übernommen, wenn die entsprechende Option aktiviert ist.
    """
    __tablename__ = "shared_dimension_answer"
    id = db.Column(db.Integer, primary_key=True)
    dimension_id = db.Column(db.Integer, db.ForeignKey("dimension.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("question.id"), nullable=False)
    scale_option_id = db.Column(db.Integer, db.ForeignKey("scale_option.id"), nullable=True)
    numeric_value = db.Column(db.Float, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint(
            "dimension_id",
            "question_id",
            "scale_option_id",
            name="uq_shared_dimension_answer_dim_question_option",
        ),
    )

    # Beziehungen
    dimension_obj = db.relationship('Dimension', backref='shared_answers')
    question_obj = db.relationship('Question', backref='shared_answers')
    scale_option = db.relationship('ScaleOption', backref='shared_answers')
