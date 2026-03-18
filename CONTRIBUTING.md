# Contributing to OmniSignal

Thank you for your interest in contributing to OmniSignal! This document provides guidelines for contributing to the project.

## Development Setup

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/omnisignal.git`
3. Create a virtual environment: `python -m venv .venv`
4. Activate it: `source .venv/bin/activate` (or `.venv\Scripts\activate` on Windows)
5. Install dependencies: `pip install -r requirements.txt`
6. Copy `.env.example` to `.env` and add your API keys
7. Install dashboard dependencies: `cd dashboard && npm install`

## Running Tests

```bash
# Run all tests with coverage
python -m pytest tests/ -v --cov=src --cov-report=html

# Run specific test file
python -m pytest tests/test_risk_analysis.py -v

# Run with verbose output
python -m pytest tests/ -vv --tb=short
```

## Code Style

- Python: Follow PEP 8 guidelines
- TypeScript/React: Follow the existing code style
- Use type hints in Python code
- Add docstrings to all public functions and classes

## Pull Request Process

1. Create a new branch: `git checkout -b feature/your-feature-name`
2. Make your changes
3. Add tests for new functionality
4. Ensure all tests pass: `pytest tests/`
5. Update documentation if needed
6. Commit with a descriptive message: `git commit -m "feat: add new feature"`
7. Push to your fork: `git push origin feature/your-feature-name`
8. Open a Pull Request

## Commit Message Format

Use conventional commits:

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `test:` Adding or updating tests
- `refactor:` Code refactoring
- `perf:` Performance improvements
- `chore:` Maintenance tasks

Examples:
- `feat: add sentiment caching for faster responses`
- `fix: handle missing FRED data gracefully`
- `docs: update API endpoint documentation`

## Adding New Features

### Adding a New Data Source

1. Create a new module in `src/` (e.g., `src/new_source.py`)
2. Define Pydantic models in `src/models.py`
3. Add integration to `src/data_pipeline.py`
4. Write tests in `tests/test_new_source.py`
5. Update documentation

### Adding a New API Endpoint

1. Add endpoint to `api/index.py`
2. Follow existing patterns for error handling
3. Keep response times under 10 seconds (Vercel limit)
4. Add endpoint documentation to README.md

### Adding Dashboard Components

1. Create component in `dashboard/src/components/`
2. Follow existing styling patterns (Tailwind + CSS variables)
3. Ensure responsive design (mobile-first)
4. Add TypeScript types

## Testing Guidelines

- Aim for 80%+ code coverage
- Test both success and error cases
- Mock external API calls
- Use fixtures for common test data (see `tests/conftest.py`)

## Documentation

- Update README.md for user-facing changes
- Update DEPLOYMENT.md for deployment-related changes
- Add inline comments for complex logic
- Update docstrings when changing function signatures

## Questions?

Open an issue or discussion on GitHub if you have questions about contributing.

## License

By contributing, you agree that your contributions will be licensed under the same license as the project.
