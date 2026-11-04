# PyMSScreen - Codex Instructions

## Project objective
Integrate PyMSScreen into Galaxy while preserving
the existing scientific functionality.

## Target architecture
The integration should consist of four Galaxy tools:

1. Data preparation
2. EIC/MS2 extraction
3. Prescreening and quality control
4. Interactive visualization and exports

The fourth component should use Galaxy Interactive Tools.

## Development principles
- Reuse existing Python functions whenever possible.
- Preserve the existing React/Flask application.
- Avoid unnecessary refactoring.
- Do not modify scientific algorithms without approval.
- Do not change scientific parameter defaults without approval.
- Maintain compatibility with the existing application.
- Follow Galaxy IUC best practices.
- Prioritize reproducibility and traceability.

## Working methodology
1. Analyze existing code before proposing changes.
2. Explain the proposed implementation.
3. Wait for explicit approval before modifying files.
4. Implement one component at a time.
5. Add relevant tests.
6. Report modified files and test results.

## Testing
- Use Planemo for Galaxy wrapper validation.
- Compare Galaxy results with existing PyMSScreen results.
- Test with representative mzML datasets.
- Report test failures explicitly.

## Restrictions
- Never commit or push without approval.
- Never delete files without approval.
- Never modify production Galaxy configurations.
- Never expose credentials or sensitive datasets.
- Never use emoji in code 