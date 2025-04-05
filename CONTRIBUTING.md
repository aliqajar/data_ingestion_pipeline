# Contributing to Weather System Pipeline

Thank you for your interest in contributing to the Weather System Pipeline project! This document provides guidelines and instructions for contributing.

## Development Workflow

1. **Fork the Repository**: Start by forking the repository to your GitHub account.

2. **Clone Your Fork**: Clone your fork to your local machine:
   ```bash
   git clone https://github.com/your-username/weather-system-pipeline.git
   cd weather-system-pipeline
   ```

3. **Create a Branch**: Create a new branch for your feature or bugfix:
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/issue-description
   ```

4. **Make Changes**: Implement your changes, following the code style of the project.

5. **Run Tests**: Make sure all tests pass before submitting your changes:
   ```bash
   docker compose run --rm test
   ```

6. **Commit Changes**: Commit your changes with a descriptive message:
   ```bash
   git commit -am "Add feature: description of your changes"
   ```

7. **Push Changes**: Push your branch to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```

8. **Create a Pull Request**: Go to the original repository and create a pull request from your branch.

## Pull Request Process

1. Fill out the pull request template with all required information.
2. Ensure all tests are passing in the CI pipeline.
3. Update documentation if your changes affect the user experience or API.
4. The maintainers will review your PR and provide feedback.
5. Once approved, your PR will be merged into the main branch.

## Continuous Integration

All pull requests are automatically tested with our CI pipeline. The pipeline:

1. Runs all unit and integration tests
2. Checks code style and linting
3. Ensures documentation is up to date

Your PR cannot be merged until all CI checks pass.

## Code Style and Standards

- Follow PEP 8 guidelines for Python code
- Use meaningful variable and function names
- Write descriptive docstrings for functions and classes
- Keep functions short and focused on a single task
- Include unit tests for new features and bug fixes

## Issues and Feature Requests

- Use the GitHub Issues tab to report bugs or suggest features
- Check existing issues to avoid duplicates
- Provide detailed steps to reproduce bugs
- Include system information when reporting issues

## Setting Up Branch Protection

For repository administrators, set up branch protection rules:

1. Go to Settings > Branches > Add rule
2. Add "main" as the branch pattern
3. Enable "Require status checks to pass before merging"
4. Select the CI workflow status checks
5. Optionally enable "Require pull request reviews before merging"

This ensures all code in the main branch passes tests and meets quality standards. 