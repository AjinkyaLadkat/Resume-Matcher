"""Deterministic skill-overlap gate for semantic scoring.

This module exists because embedding cosine similarity alone cannot detect
domain mismatch. Two resumes from completely unrelated fields (e.g. Data
Analytics vs Retail Operations) both contain professional English — verbs,
nouns, workplace nouns — and land in the same 0.30-0.45 cosine range that
genuinely related but differently-worded pairs also occupy. Cosine similarity
measures "is this professionally-written text," not "does this candidate
have the skills this job needs."

The fix: compute literal/fuzzy overlap between JD required_skills and the
resume's skill + experience + project text, and use that as a hard multiplier
on the final score. A resume with zero required-skill evidence gets capped
low regardless of how "well-written" its unrelated content is.

This is intentionally NOT an LLM call — it must be fast, deterministic, and
reproducible for the benchmark suite in tests/test_scoring_calibration.py.
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Generic/soft skills that should contribute minimally to overlap scoring —
# present in nearly every job description regardless of domain, so matching
# on these alone is not evidence of domain fit.
_GENERIC_SOFT_SKILLS = {
    "communication", "communication skills", "teamwork", "team player",
    "leadership", "problem solving", "problem-solving", "time management",
    "organization", "organizational skills", "attention to detail",
    "interpersonal skills", "collaboration", "adaptability", "flexibility",
    "customer service", "multitasking", "critical thinking", "work ethic",
    "self-motivated", "detail-oriented", "fast-paced environment",
    "professionalism", "reliability", "punctuality", "positive attitude",
}


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation noise, collapse whitespace."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s+#./-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _is_generic(skill: str) -> bool:
    return _normalize(skill) in _GENERIC_SOFT_SKILLS


# ═══════════════════════════════════════════════════════════════════════════
# Skill taxonomy — curated canonical-skill equivalences.
#
# This is NOT a general fuzzy/synonym engine. Each group below is a closed
# set of names that are genuine alternate phrasings of *one* underlying
# skill — abbreviations, vendor/product names, common resume wording, and
# (for a handful of tightly-coupled cases, e.g. Python's core data stack)
# the specific libraries that only make sense as evidence of that skill.
#
# What this deliberately does NOT do: map between *different*, competing
# tools or skills. Power BI is never evidence for Tableau. React is never
# evidence for Angular. Kubernetes is never evidence for Docker. Those are
# substitutes a candidate could lack one of, not alternate spellings of the
# same requirement — conflating them would manufacture false positives.
#
# Every group is built with `_syn(...)`, which normalizes each name and maps
# every member to the full set of members. That makes the table symmetric
# and order-independent: it doesn't matter whether the JD's literal skill
# text is "ReactJS" or "React.js" or "React" — all three resolve to the same
# evidence set. Groups are merged with `_merge(...)`, which unions alias
# sets on key collision rather than silently overwriting, so an accidental
# duplicate definition can never quietly drop entries.
#
# Curation rules followed throughout (precision over recall):
#   - No bare 2-3 letter abbreviation is added as an alias when it has a
#     common non-technical meaning that could appear in unrelated resumes
#     (e.g. no bare "cv" for Computer Vision — "CV" commonly means résumé;
#     no bare "ml" for Machine Learning — "ml" is a volume unit; no bare
#     "bi" for Business Intelligence — collides with "bi-weekly"/"bi-annual").
#   - No alias is a common English word/adjective on its own. Some
#     *canonical* skill names are unavoidably common words (Go, Rust, R, C,
#     Swift, Dart) because that's literally the language's name as it
#     appears in JDs — that pre-existing ambiguity isn't introduced or
#     amplified here, and no extra generic-word aliases are layered on top.
#   - Skills whose canonical name normalizes to an ordinary English word
#     are omitted outright rather than risk it — e.g. "SAFe" (Scaled Agile
#     Framework) is left out because it normalizes to "safe".
#   - Library-to-language merges are limited to cases where the library is
#     effectively single-ecosystem (Pandas/NumPy/Matplotlib only run under
#     Python); general frameworks/tools keep their own separate entries.
# ═══════════════════════════════════════════════════════════════════════════


def _syn(*names: str) -> dict[str, frozenset[str]]:
    """Build one synonym group: every name maps to the full normalized set."""
    norm = frozenset(n for n in (_normalize(x) for x in names) if n)
    return {n: norm for n in norm}


def _merge(*groups: dict[str, frozenset[str]]) -> dict[str, frozenset[str]]:
    """Merge synonym groups, unioning aliases on any key collision."""
    merged: dict[str, frozenset[str]] = {}
    for group in groups:
        for key, aliases in group.items():
            merged[key] = merged.get(key, frozenset()) | aliases
    return merged


# ── Software Engineering: programming languages ───────────────────────────
_LANGUAGES = [
    _syn("Python", "Pandas", "NumPy", "Matplotlib", "Python Scripting", "Python Programming"),
    _syn("Java", "Java Programming", "Core Java", "J2EE", "Java EE"),
    _syn("JavaScript", "JS", "ES6", "ECMAScript", "Vanilla JavaScript"),
    _syn("TypeScript", "TS"),
    _syn("C++", "CPP", "C Plus Plus"),
    _syn("C#", "C Sharp", "CSharp"),
    _syn("C", "C Programming", "ANSI C"),
    _syn("Go", "Golang"),
    _syn("Rust", "Rust Programming Language", "Rustlang"),
    _syn("Ruby", "Ruby Programming"),
    _syn("PHP", "PHP Programming"),
    _syn("Swift", "Swift Programming Language"),
    _syn("Kotlin"),
    _syn("Scala"),
    _syn("R", "R Programming", "R Language", "RStudio"),
    _syn("MATLAB"),
    _syn("Perl", "Perl Scripting"),
    _syn("Bash", "Bash Scripting", "Shell Scripting", "Shell", "Unix Shell"),
    _syn("PowerShell", "PowerShell Scripting"),
    _syn("Dart", "Dart Programming Language"),
    _syn("Objective-C", "ObjC", "Objective C"),
    _syn("Julia"),
    _syn("Haskell"),
    _syn("Elixir"),
    _syn("Clojure"),
    _syn("VB.NET", "Visual Basic .NET", "Visual Basic"),
    _syn("COBOL"),
    _syn("Fortran"),
    _syn("Assembly Language", "Assembly Programming"),
    _syn(".NET", ".NET Framework", ".NET Core", "Dotnet", "DotNet"),
]

# ── Software Engineering: frontend web ─────────────────────────────────────
_FRONTEND = [
    _syn("HTML", "HTML5"),
    _syn("CSS", "CSS3"),
    _syn("Sass", "SCSS", "Sass/SCSS"),
    _syn("Less", "Less CSS"),
    _syn("Tailwind CSS", "TailwindCSS", "Tailwind"),
    _syn("Bootstrap", "Bootstrap CSS"),
    _syn("React", "React.js", "ReactJS"),
    _syn("Redux", "Redux.js", "Redux Toolkit"),
    _syn("Angular", "AngularJS", "Angular.js"),
    _syn("Vue.js", "Vue", "VueJS"),
    _syn("Svelte", "SvelteKit"),
    _syn("jQuery"),
    _syn("Next.js", "NextJS"),
    _syn("Nuxt.js", "NuxtJS"),
    _syn("Webpack"),
    _syn("Vite"),
    _syn("Babel", "Babel.js"),
    _syn("Material UI", "MUI", "Material-UI"),
    _syn("Responsive Web Design", "Responsive Design"),
    _syn("Web Accessibility", "WCAG", "ARIA", "Accessibility Standards"),
    _syn("Progressive Web Apps", "PWA", "Progressive Web App"),
    _syn("Web Components"),
    _syn("WebAssembly", "WASM"),
]

# ── Software Engineering: backend & APIs ───────────────────────────────────
_BACKEND = [
    _syn("Node.js", "NodeJS", "Node"),
    _syn("Express.js", "ExpressJS", "Express"),
    _syn("Django", "Django REST Framework", "DRF"),
    _syn("Flask"),
    _syn("FastAPI"),
    _syn("Ruby on Rails", "Rails", "RoR"),
    _syn("Spring Boot", "Spring Framework", "Spring"),
    _syn("ASP.NET", "ASP.NET Core", "ASP.NET MVC"),
    _syn("Laravel"),
    _syn("Symfony"),
    _syn("NestJS", "Nest.js"),
    _syn("GraphQL"),
    _syn("REST API", "RESTful API", "REST", "RESTful Services", "REST APIs"),
    _syn("gRPC"),
    _syn("Microservices", "Microservice Architecture"),
    _syn("API Development", "API Design"),
    _syn("SOAP", "Web Services", "SOAP API"),
    _syn("WebSockets", "Websocket"),
]

# ── Databases ───────────────────────────────────────────────────────────────
_DATABASES = [
    _syn(
        "SQL", "MySQL", "PostgreSQL", "Postgres", "SQL Server", "T-SQL",
        "TSQL", "PL/SQL", "PLSQL", "Oracle SQL", "MSSQL", "SQLite",
        "SQL Queries", "Query Optimization",
    ),
    _syn("Oracle Database", "Oracle DB", "Oracle RDBMS"),
    _syn("MongoDB", "Mongo"),
    _syn("Cassandra", "Apache Cassandra"),
    _syn("Redis"),
    _syn("DynamoDB", "Amazon DynamoDB"),
    _syn("Elasticsearch"),
    _syn("Neo4j", "Graph Database", "Graph Databases"),
    _syn("MariaDB"),
    _syn("NoSQL", "NoSQL Databases"),
    _syn("Database Design", "Database Modeling", "Data Modeling", "Schema Design"),
    _syn("Database Administration", "DBA", "Database Administrator"),
    _syn("ETL", "Extract Transform Load", "ETL Pipelines", "ETL Development"),
    _syn("Stored Procedures"),
    _syn("Database Normalization"),
    _syn("Database Indexing", "Indexing Strategies"),
    _syn("Database Performance Tuning", "Query Tuning"),
]

# ── Data Analytics / Business Intelligence ─────────────────────────────────
_DATA_ANALYTICS = [
    _syn("Microsoft Excel", "Excel", "MS Excel", "Advanced Excel", "Excel VBA", "Pivot Tables"),
    _syn(
        "Power BI", "Microsoft Power BI", "PowerBI", "Power BI Dashboards",
        "Power BI Reports", "Power Query", "DAX",
    ),
    _syn("Tableau", "Tableau Desktop", "Tableau Dashboards"),
    _syn("Looker", "Looker Studio", "Google Data Studio"),
    _syn("QlikView", "Qlik Sense", "Qlik"),
    _syn(
        "KPI Reporting", "KPI Analysis", "KPI Dashboard", "KPI Dashboards",
        "KPI Tracking", "Key Performance Indicator", "Key Performance Indicators",
    ),
    _syn(
        "Data Visualization", "Data Visualisation", "Data Viz", "Dashboard",
        "Dashboards", "Interactive Dashboard", "Interactive Dashboards", "Dashboarding",
    ),
    _syn(
        "Data Cleaning", "Data Cleansing", "Data Transformation",
        "Data Wrangling", "Data Preprocessing", "Data Munging",
    ),
    _syn("Data Analysis", "Data Analytics", "Exploratory Data Analysis", "EDA"),
    _syn("Statistics Fundamentals", "Statistical Analysis", "Statistics", "Statistical Modeling"),
    _syn("A/B Testing", "Split Testing", "AB Testing"),
    _syn("Google Analytics", "GA4"),
    _syn("SPSS"),
    _syn("SAS", "SAS Programming"),
    _syn("Business Intelligence", "BI Reporting", "BI Dashboard", "BI Tools", "BI Development"),
    _syn("Data Storytelling"),
]

# ── Data Engineering ─────────────────────────────────────────────────────────
_DATA_ENGINEERING = [
    _syn("Apache Airflow", "Airflow"),
    _syn("Apache Spark", "PySpark", "Spark"),
    _syn("Apache Kafka", "Kafka"),
    _syn("Apache Hadoop", "Hadoop", "HDFS"),
    _syn("Data Warehousing", "Data Warehouse"),
    _syn("Snowflake"),
    _syn("Amazon Redshift", "Redshift"),
    _syn("Google BigQuery", "BigQuery"),
    _syn("dbt", "Data Build Tool"),
    _syn("Data Pipeline", "Data Pipelines", "Pipeline Development", "Pipeline Engineering"),
    _syn("Apache NiFi", "NiFi"),
    _syn("Databricks"),
    _syn("Apache Beam"),
    _syn("Data Lake", "Data Lakehouse", "Data Lakes"),
    _syn("Apache Flink", "Flink"),
]

# ── AI / Machine Learning ───────────────────────────────────────────────────
_AI_ML = [
    _syn("Machine Learning", "Applied Machine Learning", "ML Engineering", "ML Modeling"),
    _syn("Deep Learning"),
    _syn("Natural Language Processing", "NLP"),
    _syn("Computer Vision"),
    _syn("TensorFlow"),
    _syn("Keras"),
    _syn("PyTorch", "Torch"),
    _syn("Scikit-learn", "sklearn", "Scikit Learn"),
    _syn("Seaborn"),
    _syn("Hugging Face", "HuggingFace", "HuggingFace Transformers", "Transformers Library"),
    _syn("OpenCV"),
    _syn("XGBoost"),
    _syn("LightGBM"),
    _syn("CatBoost"),
    _syn("Reinforcement Learning"),
    _syn("Generative AI", "GenAI"),
    _syn("Large Language Models", "LLM", "LLMs"),
    _syn("Neural Networks", "Artificial Neural Networks"),
    _syn("MLOps"),
    _syn("Feature Engineering"),
    _syn("Model Deployment", "ML Model Deployment"),
    _syn("Prompt Engineering"),
    _syn("Convolutional Neural Networks", "CNN", "CNNs"),
    _syn("Recurrent Neural Networks", "RNN", "RNNs"),
    _syn("Transformer Models", "Transformer Architecture"),
]

# ── Cloud ────────────────────────────────────────────────────────────────────
_CLOUD = [
    _syn("Amazon Web Services", "AWS"),
    _syn("AWS EC2", "Amazon EC2", "EC2"),
    _syn("AWS S3", "Amazon S3", "S3", "Simple Storage Service"),
    _syn("AWS Lambda", "Lambda Functions", "AWS Lambda Functions"),
    _syn("Microsoft Azure", "Azure"),
    _syn("Azure DevOps"),
    _syn("Azure Functions"),
    _syn("Google Cloud Platform", "GCP", "Google Cloud"),
    _syn("Google Compute Engine", "GCE"),
    _syn("Cloud Functions", "GCP Cloud Functions"),
    _syn("Cloud Architecture", "Cloud Computing"),
    _syn("Serverless", "Serverless Computing", "Serverless Architecture"),
    _syn("AWS CloudFormation", "CloudFormation"),
    _syn("Virtual Private Cloud", "VPC"),
    _syn("Cloud Migration"),
]

# ── DevOps / Infrastructure ─────────────────────────────────────────────────
_DEVOPS = [
    _syn("Docker", "Containerization", "Docker Containers"),
    _syn("Kubernetes", "K8s", "Container Orchestration"),
    _syn("Terraform", "Infrastructure as Code", "IaC"),
    _syn("Ansible"),
    _syn("Jenkins", "Jenkins CI"),
    _syn("CI/CD", "Continuous Integration", "Continuous Deployment", "Continuous Delivery"),
    _syn("GitLab CI", "GitLab CI/CD"),
    _syn("GitHub Actions"),
    _syn("Helm", "Helm Charts"),
    _syn("Prometheus"),
    _syn("Grafana"),
    _syn("Linux Administration", "Linux System Administration", "Linux Admin"),
    _syn("Configuration Management"),
    _syn("Chef"),
    _syn("Puppet"),
    _syn("Nagios"),
    _syn("ELK Stack", "Elastic Stack", "Logstash", "Kibana"),
    _syn("Site Reliability Engineering", "SRE"),
    _syn("Observability", "Monitoring and Alerting"),
]

# ── Cybersecurity ────────────────────────────────────────────────────────────
_CYBERSECURITY = [
    _syn("Network Security"),
    _syn("Penetration Testing", "Pen Testing", "Ethical Hacking"),
    _syn("SIEM", "Security Information and Event Management"),
    _syn("Firewall Management", "Firewall Configuration"),
    _syn("Vulnerability Assessment", "Vulnerability Management", "Vulnerability Scanning"),
    _syn("Cryptography", "Encryption"),
    _syn("Identity and Access Management", "IAM"),
    _syn("Security Operations Center", "SOC"),
    _syn("Incident Response"),
    _syn("Malware Analysis"),
    _syn("OWASP", "OWASP Top 10"),
    _syn("Security Auditing", "Security Audits"),
    _syn("Regulatory Compliance", "Compliance"),
    _syn("ISO 27001"),
    _syn("NIST Framework", "NIST"),
    _syn("CISSP"),
    _syn("Threat Intelligence"),
    _syn("Endpoint Security"),
    _syn("Zero Trust", "Zero Trust Architecture"),
]

# ── Mobile Development ───────────────────────────────────────────────────────
_MOBILE = [
    _syn("Android Development", "Android App Development"),
    _syn("iOS Development", "iOS App Development"),
    _syn("React Native"),
    _syn("Flutter"),
    _syn("Xamarin"),
    _syn("Mobile UI/UX", "Mobile App Design"),
    _syn("Cordova", "Apache Cordova"),
    _syn("SwiftUI"),
    _syn("Jetpack Compose"),
]

# ── QA / Testing ──────────────────────────────────────────────────────────────
_QA = [
    _syn("Manual Testing"),
    _syn("Automated Testing", "Test Automation"),
    _syn("Selenium", "Selenium WebDriver"),
    _syn("Cypress"),
    _syn("JUnit"),
    _syn("TestNG"),
    _syn("Postman", "Postman API Testing"),
    _syn("JMeter", "Apache JMeter"),
    _syn("Test Case Design", "Test Case Writing"),
    _syn("Regression Testing"),
    _syn("Performance Testing"),
    _syn("Load Testing"),
    _syn("API Testing"),
    _syn("Appium"),
    _syn("Unit Testing"),
    _syn("Integration Testing"),
    _syn("Test-Driven Development", "TDD"),
    _syn("Behavior-Driven Development", "BDD"),
]

# ── Project Management / Methodology ────────────────────────────────────────
# Note: "SAFe" (Scaled Agile Framework) is deliberately omitted — it
# normalizes to the common English word "safe" and would create
# unacceptable false-positive risk (see taxonomy header note above).
_PROJECT_MANAGEMENT = [
    _syn("Agile", "Agile Methodology", "Agile Development"),
    _syn("Scrum", "Scrum Master"),
    _syn("Kanban"),
    _syn("JIRA", "Atlassian JIRA"),
    _syn("Confluence"),
    _syn("Waterfall", "Waterfall Methodology"),
    _syn("Sprint Planning", "Sprint Management"),
    _syn("PMP", "Project Management Professional"),
]

# ── Version Control ──────────────────────────────────────────────────────────
_VERSION_CONTROL = [
    _syn("Git", "Git Version Control"),
    _syn("GitHub"),
    _syn("GitLab"),
    _syn("Bitbucket"),
    _syn("SVN", "Subversion"),
]

# ── Operating Systems / Networking ──────────────────────────────────────────
_OS_NETWORKING = [
    _syn("Linux"),
    _syn("Windows Server"),
    _syn("Unix"),
    _syn("macOS", "Mac OS"),
    _syn("TCP/IP"),
    _syn("DNS", "Domain Name System"),
    _syn("VPN", "Virtual Private Network"),
    _syn("Load Balancing"),
    _syn("Network Administration"),
    _syn("CCNA", "Cisco Certified Network Associate"),
]

# ── ERP / CRM / Business Platforms ──────────────────────────────────────────
_ERP_CRM = [
    _syn("Salesforce", "Salesforce CRM", "Salesforce Administration"),
    _syn("SAP", "SAP ERP"),
    _syn("Oracle ERP", "Oracle E-Business Suite"),
    _syn("Microsoft Dynamics", "Dynamics 365"),
    _syn("HubSpot", "HubSpot CRM"),
]

_SKILL_SYNONYMS: dict[str, frozenset[str]] = _merge(
    *_LANGUAGES, *_FRONTEND, *_BACKEND, *_DATABASES, *_DATA_ANALYTICS,
    *_DATA_ENGINEERING, *_AI_ML, *_CLOUD, *_DEVOPS, *_CYBERSECURITY,
    *_MOBILE, *_QA, *_PROJECT_MANAGEMENT, *_VERSION_CONTROL,
    *_OS_NETWORKING, *_ERP_CRM,
)


def _phrase_in_text(phrase: str, haystack_normalized: str) -> bool:
    """Word-boundary-safe check for an exact (already-normalized) phrase.

    Deliberately NOT a plain substring ("in") check — that would let
    "java" match inside "javascript" or "ml" match inside "html". Using
    \\b on both ends of the (possibly multi-word) phrase means it only
    counts when the phrase appears as its own token(s) in the text.
    """
    if not phrase:
        return False
    return bool(re.search(rf"\b{re.escape(phrase)}\b", haystack_normalized))


def _skill_found_in_text(skill: str, haystack_normalized: str) -> bool:
    """Word-boundary-safe containment check, with a curated synonym table.

    Resolution order (first hit wins):
      1. Curated synonym match — same skill, different unambiguous wording
         (see _SKILL_SYNONYMS). This is what recognizes "SQL" evidenced by
         "MySQL", or "Data Cleaning" evidenced by "data transformation".
      2. Exact phrase match against the skill's own normalized text.
      3. Multi-word fallback — every significant word of the skill appears
         somewhere in the haystack as its own word. Guards against JD
         phrasing like "proficiency in SQL" vs resume listing just "SQL".
    No naive substring fallback is used, to avoid false positives from
    word-fragment collisions (e.g. "Java" inside "JavaScript").
    """
    skill_norm = _normalize(skill)
    if not skill_norm:
        return False

    synonyms = _SKILL_SYNONYMS.get(skill_norm)
    if synonyms and any(_phrase_in_text(alt, haystack_normalized) for alt in synonyms):
        return True

    if _phrase_in_text(skill_norm, haystack_normalized):
        return True

    words = [w for w in skill_norm.split() if len(w) > 2]
    if len(words) >= 2:
        return all(_phrase_in_text(w, haystack_normalized) for w in words)

    return False


def compute_skill_overlap(
    resume_data: dict[str, Any],
    jd_keywords: dict[str, Any],
) -> dict[str, Any]:
    """Compute literal/fuzzy overlap between JD requirements and resume content.

    Returns a dict with:
        required_total:     count of non-generic required skills in the JD
        required_matched:   how many of those were found in the resume
        required_match_rate: required_matched / required_total (0.0-1.0)
        preferred_match_rate: same, for preferred_skills
        matched_skills:      list of matched skill names (for debugging/UI)
        missing_critical:    required skills with zero evidence
    """
    haystack = _build_resume_haystack(resume_data)
    haystack_norm = _normalize(haystack)

    required = [s for s in jd_keywords.get("required_skills", []) if isinstance(s, str) and s.strip()]
    preferred = [s for s in jd_keywords.get("preferred_skills", []) if isinstance(s, str) and s.strip()]

    # Filter out generic soft skills from the "critical" count — matching on
    # "communication" tells us nothing about domain fit.
    required_specific = [s for s in required if not _is_generic(s)]

    matched_skills: list[str] = []
    missing_critical: list[str] = []
    for skill in required_specific:
        if _skill_found_in_text(skill, haystack_norm):
            matched_skills.append(skill)
        else:
            missing_critical.append(skill)

    required_total = len(required_specific)
    required_matched = len(matched_skills)
    required_match_rate = (required_matched / required_total) if required_total else 1.0
    # No required skills extracted at all → don't penalise (upstream extraction
    # may have failed); treat as neutral rather than as a mismatch signal.

    preferred_matched = sum(
        1 for s in preferred if not _is_generic(s) and _skill_found_in_text(s, haystack_norm)
    )
    preferred_specific_total = len([s for s in preferred if not _is_generic(s)])
    preferred_match_rate = (
        (preferred_matched / preferred_specific_total) if preferred_specific_total else 1.0
    )

    return {
        "required_total": required_total,
        "required_matched": required_matched,
        "required_match_rate": round(required_match_rate, 3),
        "preferred_match_rate": round(preferred_match_rate, 3),
        "matched_skills": matched_skills,
        "missing_critical": missing_critical,
    }


def _build_resume_haystack(resume_data: dict[str, Any]) -> str:
    """Concatenate all resume text where a skill could legitimately appear.

    Includes: technical skills list, certifications, summary, experience
    bullets, project bullets. Deliberately excludes personal info, education
    institution names, and dates — those are never where a skill claim lives.
    """
    parts: list[str] = []

    additional = resume_data.get("additional", {}) or {}
    for key in ("technicalSkills", "certificationsTraining", "languages"):
        val = additional.get(key, [])
        if isinstance(val, list):
            parts.extend(str(v) for v in val)

    summary = resume_data.get("summary", "")
    if isinstance(summary, str):
        parts.append(summary)

    for exp in resume_data.get("workExperience", []) or []:
        if not isinstance(exp, dict):
            continue
        parts.append(str(exp.get("title", "")))
        desc = exp.get("description", [])
        if isinstance(desc, list):
            parts.extend(str(d) for d in desc)

    for proj in resume_data.get("personalProjects", []) or []:
        if not isinstance(proj, dict):
            continue
        parts.append(str(proj.get("name", "")))
        desc = proj.get("description", [])
        if isinstance(desc, list):
            parts.extend(str(d) for d in desc)

    return " ".join(p for p in parts if p)

