# AI Agents for Supplier Risk Assessment

**Author: Armand Amoussou**

Systeme multi-agents (CrewAI) pour le scoring et l'anticipation du risque fournisseur. Pipeline batch quotidien produisant un score global multi-criteres avec tracabilite des preuves, historisation, et alerting.

## Architecture

### Vue C4 simplifiee

**Context**: Les equipes Achats/Supply Chain utilisent le systeme pour evaluer et anticiper les risques fournisseurs. Le systeme collecte des donnees internes et externes, applique un scoring multi-criteres, et genere des alertes.

**Containers**:
- **CLI Runner** : Point d'entree (cron/on-demand) via Click
- **CrewAI Runtime** : Orchestration des 7 agents (Collector, Normalizer, FinancialScorer, InternalRulesScorer, RiskAggregator, Notifier, Auditor)
- **Scraper** : Collecte web avec allowlist, robots.txt, rate limiting, cache
- **DB** : PostgreSQL (principal) / DuckDB (fallback)
- **Notifier** : Alertes dry-run (fichiers) ou SMTP (MailHog)
- **Exporter** : CSV/JSON
- **Observability** : Logs JSON structures, audit trail

### Sequence batch quotidienne

```
CLI run-daily(date)
  -> Load config + suppliers
  -> Init DB + tools
  -> For each supplier:
      -> Ingest internal signals (C1, C2, C3 deterministes)
      -> Collect official web data (allowlist + robots.txt + rate limit + cache)
      -> Normalize content (trafilatura + bs4)
      -> Financial scoring via LLM (JSON strict + anti-hallucination)
      -> Aggregate global score (weighted sum)
      -> Check alerting conditions
      -> Persist all results
  -> Export CSV/JSON
  -> Finalize audit trail
```

### Composants

| Composant | Tech | Role | Entrees | Sorties | Securite |
|-----------|------|------|---------|---------|----------|
| CLI | Click | Point d'entree | Args CLI | Pipeline result | - |
| Collector | requests | Fetch web | URLs allowlist | HTML brut | allowlist, robots.txt, rate limit |
| Normalizer | trafilatura/bs4 | Parse HTML | HTML brut | Snippets texte | - |
| FinancialScorer | OpenAI/Ollama | Score LLM | Snippets | JSON score | Anti-hallucination, validation |
| InternalRulesScorer | Python pur | Score regles | Signals internes | C1,C2,C3 | Deterministe |
| RiskAggregator | Python pur | Score global | 4 scores | Score + niveau | Poids configurables |
| Notifier | smtplib/fichiers | Alertes | Score + seuils | Alert payload | dry-run par defaut |
| DB | psycopg2/duckdb | Persistance | Scores | Historique | Secrets en env vars |
| Exporter | csv/json | Export | Scores DB | Fichiers | - |
| Audit | structlog | Tracabilite | Run metadata | Log JSON | - |

## Criteres de scoring

### Criteres internes (deterministes)
- **C1 - Performance livraison** (poids: 20%) : retards, severite, incidents qualite
- **C2 - Dependance / criticite** (poids: 15%) : monosource, criticite composants
- **C3 - Historique relation** (poids: 15%) : maturite contrat, litiges

### Critere financier (LLM)
- **C4 - Risque financier** (poids: 50%) : analyse LLM de sources officielles publiques

### Score global
- `global_score = sum(Ci * Wi)` avec somme des poids = 1.0
- HIGH >= 70, MEDIUM >= 55, LOW < 55

## Prerequis

- Linux (VM ou local)
- Python 3.11
- Docker + Docker Compose (recommande pour PostgreSQL)
- Cle API OpenAI (ou Ollama installe localement)

## Installation (From Zero to Run)

```bash
# 1. Cloner le repo
git clone <repo-url>
cd ai-agents-for-supplier-risk-assessment

# 2. Lancer le bootstrap
bash scripts/bootstrap.sh

# 3. Activer l'environnement
source .venv/bin/activate

# 4. Configurer les variables d'environnement
# Editer .env : configurer OPENAI_API_KEY ou passer en mode golden

# 5. Mode golden (sans internet, sans API LLM)
export GOLDEN_MODE=1

# 6. Seed de la base de donnees
make seed

# 7. Lancer le pipeline
make run

# 8. Verifier les sorties
ls -la out/
```

## Utilisation

### Commandes principales

```bash
# Pipeline quotidien (date du jour)
make run

# Pipeline pour une date specifique
make run-date DATE=2026-01-15

# Pipeline en mode golden (offline)
make run-golden

# Exporter les scores
make export

# Seeder la base
make seed
```

### Tests

```bash
# Tous les tests
make test

# Tests golden uniquement
make test-golden

# Lint
make lint

# Type checking
make typecheck
```

### Docker

```bash
# Demarrer PostgreSQL
make docker-up

# Demarrer PostgreSQL + MailHog
make docker-up-mail

# Arreter
make docker-down
```

## Mode sans internet (golden)

Le mode golden utilise des donnees de test locales dans `app/golden/`:
- `cases/` : fichiers texte simulant des sources officielles
- `expected/` : resultats attendus pour validation

Activer avec `GOLDEN_MODE=1` ou `make run-golden`.

## Alerting

Declenchement si :
1. Passage MEDIUM -> HIGH
2. Variation global_score >= +15 sur 7 jours
3. Driver critique detecte (DEFAULT, INSOLVENCY, PROCEEDING, BANKRUPTCY, LIQUIDATION)

Mode par defaut : dry-run (fichiers JSON dans `./out/alerts/`).
Mode SMTP : configurer MailHog via `make docker-up-mail`.

## Structure du projet

```
app/
  crew/          # CrewAI agents, tasks, crew definition
  tools/         # Web fetch, parse, cache, rate limit, scoring, LLM, etc.
  pipelines/     # Pipeline steps and daily orchestrator
  schemas/       # Pydantic v2 schemas
  configs/       # YAML configs, SQL schema, settings
  golden/        # Test data (cases + expected)
  observability/ # Structured logging, audit
  cli/           # Click CLI entry point
tests/           # pytest test suite
docker/          # docker-compose.yml
scripts/         # bootstrap, run, cron
```

## Securite

- Allowlist de domaines (YAML) pour le scraping
- Respect de robots.txt (urllib.robotparser)
- Rate limiting par domaine (token bucket)
- User-Agent explicite
- Cache local avec content_hash
- Secrets via variables d'environnement (.env)
- Logs rediges sans donnees sensibles
- JSON strict valide par schema Pydantic v2
- Anti-hallucination : evidence obligatoire, INDETERMINATE si insuffisant
