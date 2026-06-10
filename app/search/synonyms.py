"""Skill synonym list for Elasticsearch synonym token filter.

Add entries as comma-separated equivalents.  The list is consumed at
index-creation time to build a synonym_graph filter; you can extend it
without re-deploying code — just re-create (or update) the index.

Languages: English canonical term + common Armenian/Russian abbreviations
are welcome here so that queries in any language match canonical skills.
"""

SKILL_SYNONYMS: list[str] = [
    # JavaScript ecosystem
    "javascript, js",
    "typescript, ts",
    "node.js, nodejs, node",
    "react.js, reactjs, react",
    "vue.js, vuejs, vue",
    "next.js, nextjs, next",
    "nuxt.js, nuxtjs, nuxt",

    # Python
    "python, py",
    "django rest framework, drf",
    "fastapi, fast api",

    # JVM
    "java, jdk",
    "kotlin, kt",
    "spring boot, springboot, spring",

    # Cloud / infra
    "kubernetes, k8s",
    "docker, dockerfile, containerization",
    "amazon web services, aws",
    "google cloud platform, gcp",
    "microsoft azure, azure",
    "infrastructure as code, iac",
    "continuous integration, ci",
    "continuous delivery, continuous deployment, cd",
    "ci/cd, cicd",

    # Data / ML
    "machine learning, ml",
    "artificial intelligence, ai",
    "natural language processing, nlp",
    "deep learning, dl",
    "tensorflow, tf",
    "pytorch, torch",
    "scikit-learn, sklearn",
    "sql, structured query language",
    "postgresql, postgres",
    "mongodb, mongo",
    "elasticsearch, elastic search, es",

    # Mobile
    "react native, react-native",
    "ios, swift",
    "android, kotlin android",

    # General
    "restful api, rest api, rest, api",
    "graphql, graph ql",
    "microservices, micro services",
    "agile, scrum, kanban",
    "test driven development, tdd",
    "behavior driven development, bdd",
    "object oriented programming, oop",
    "functional programming, fp",
    "devops, dev ops",
    "site reliability engineering, sre",
    "linux, unix",
    "git, version control",

    # Armenian/Russian abbreviations that may appear in resumes
    # (transliterated to latin for ES; Cyrillic handled by analyzer)
    "программирование, programming",
    "разработка, development",
    "аналитик, analyst",
    "менеджер, manager",
    "тестирование, testing, qa",
]
