# Contributing to Solvita

Thank you for your interest in contributing to Solvita!

## Development Setup

1. Fork and clone the repository
```bash
git clone https://github.com/S0lvita/solvita.git
cd solvita
```

2. Create a virtual environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies
```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

4. Set up configuration files
```bash
cp config/models.yaml.example config/models.yaml
cp config/neo4j.yaml.example config/neo4j.yaml
cp config/vector_db.yaml.example config/vector_db.yaml
```

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

