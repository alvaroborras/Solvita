# Contributing to Solvita

Thank you for your interest in contributing to Solvita!

## Development Setup

1. Fork and clone the repository
```bash
git clone https://github.com/NJU-LINK/Solvita.git
cd Solvita
```

2. Create a virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies
```bash
pip install -r requirements.txt
```

4. Set up configuration files
```bash
cp config/models.yaml.example config/models.yaml
# Edit config/models.yaml to set provider/base_url/model.
# NEVER write the api_key into the YAML — export OPENAI_API_KEY instead.
```

5. Install the project git hooks
```bash
./scripts/install-git-hooks.sh
```

The pre-commit hook blocks any commit that would leak an LLM API key
(including common OpenAI-style, `gsk_`, and Claude-style prefixes) into a
tracked YAML / .env / shell / markdown file. If a match is a false positive
(e.g. a sample key in docs), bypass with `git commit --no-verify`.

## Code Style

We use:
- `black` for code formatting
- `isort` for import sorting
- `mypy` for type checking
- `flake8` for linting

Run before committing:
```bash
black src/
isort src/
mypy src/
flake8 src/
```

## Testing

Run tests with:
```bash
pytest tests/
```

With coverage:
```bash
pytest --cov=src tests/
```

## Pull Request Process

1. Create a new branch for your feature
2. Make your changes
3. Add tests for new functionality
4. Ensure all tests pass
5. Update documentation if needed
6. Submit a pull request

## Code of Conduct

Please be respectful and constructive in all interactions.
