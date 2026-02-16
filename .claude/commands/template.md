# Claude Code Skill Template

This is a template for creating Claude Code skills for the AI PM Manager v2 project.

## Basic Structure

```markdown
---
description: Brief description of what this skill does
---

# Skill Name

Detailed instructions for the skill.

## Usage

Explain how to use this skill and what parameters it accepts.

## Examples

Provide example usage scenarios.
```

## Guidelines

1. **Clear Description**: Start with a concise description in the frontmatter
2. **Detailed Instructions**: Provide step-by-step instructions for the AI
3. **Context-Aware**: Include relevant project context and constraints
4. **Error Handling**: Specify how to handle common errors
5. **Output Format**: Define expected output format if applicable

## Example Skills to Reference

- `aipm-worker`: Worker role task execution
- `aipm-pm`: PM role order processing
- `aipm-status`: Project status checking

## Testing Your Skill

1. Save the skill definition in `.claude/commands/`
2. Invoke with `/skill-name` in Claude Code
3. Test with various scenarios
4. Update based on feedback

## Best Practices

- Keep instructions concise but complete
- Use consistent terminology with the project
- Include validation steps
- Document any assumptions
- Specify required tools or dependencies
