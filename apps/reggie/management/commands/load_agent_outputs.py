from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.reggie.models import AgentExpectedOutput, InstructionCategory

User = get_user_model()

class Command(BaseCommand):
    help = "Load global expected output templates using a default user"

    def handle(self, *args, **options):
        try:
            user = User.objects.get(pk=1)
        except User.DoesNotExist:
            self.stderr.write("❌ No user found with ID=1. Please create one or update the script.")
            return

        outputs = [
            {
                "title": "Research Report",
                "expected_output": """## 🧠 Expected Output Instruction: Basic Research Report

**Instruction**:  
When tasked with generating a basic research report, structure your response using the following format. Keep language formal, clear, and concise. Use bullet points and subheadings where helpful.

---

## 📘 Research Report Template

### 1. Title
- A clear and descriptive title that reflects the report's content.

### 2. Executive Summary
- A 3–5 sentence summary of the report's objective, findings, and recommendations.

### 3. Introduction
- Brief context or background information.
- Define the scope and purpose of the report.

### 4. Methodology
- Explain how the information was gathered (e.g., literature review, datasets analyzed, tools used).

### 5. Key Findings
- Present important insights or discoveries.
- Use bullet points or subheadings to organize themes.

### 6. Analysis
- Elaborate on findings with interpretation, context, or comparisons.
- Include statistics or charts if available.

### 7. Recommendations
- Provide actionable suggestions based on the findings.

### 8. Conclusion
- Summarize the main takeaways.
- Reiterate the importance or implications of the findings.

### 9. References (if applicable)
- List sources, documents, or datasets used.""",
                "category": InstructionCategory.TEMPLATE,
            },
            {
                "title": "Structured Report",
                "expected_output": """# {Report Title}

## Executive Summary
{Brief overview of key points}

## Background
{Context and relevant information}

## Analysis
{Detailed examination of the topic}
{Supporting evidence and reasoning}

## Recommendations
{Clear, actionable recommendations}
{Priority levels if applicable}

## Next Steps
{Suggested follow-up actions}

---
Report generated: {current_date}""",
                "category": InstructionCategory.RESPONSE_FORMATTING,
            },
            {
                "title": "Conversational",
                "expected_output": """I'll respond in a natural, conversational style that's easy to read and understand. I'll use:

- Simple, clear language
- Short paragraphs
- Occasional questions to check understanding
- Friendly tone throughout
- Examples when helpful
- Bullet points for lists
- **Bold text** for important points""",
                "category": InstructionCategory.RESPONSE_FORMATTING,
            },
            {
                "title": "Step-by-step guide",
                "expected_output": """# {Guide Title}

## Overview
{Brief explanation of what this guide covers}

## Prerequisites
{What you need before starting}

## Steps

1. **First Step**: {Detailed explanation}
   - {Additional notes if needed}
   - {Tips or warnings}

2. **Second Step**: {Detailed explanation}
   - {Additional notes if needed}
   - {Tips or warnings}

3. **Third Step**: {Detailed explanation}
   - {Additional notes if needed}
   - {Tips or warnings}

## Troubleshooting
{Common issues and solutions}

## Additional Resources
{Links or references for more information}""",
                "category": InstructionCategory.RESPONSE_FORMATTING,
            },
            {
                "title": "Q & A Format",
                "expected_output": """# {Topic} FAQ

## Q: {Common question about the topic}?
A: {Clear, concise answer}
- {Additional context if needed}
- {Examples if helpful}

## Q: {Another common question}?
A: {Clear, concise answer}
- {Additional context if needed}
- {Examples if helpful}

## Q: {Another common question}?
A: {Clear, concise answer}
- {Additional context if needed}
- {Examples if helpful}

## Additional Resources
{Where to find more information}""",
                "category": InstructionCategory.RESPONSE_FORMATTING,
            },
            {
                "title": "Compliance Blog Posts",
                "expected_output": """# {Title of the Blog Post}

_{One-sentence summary or hook that introduces the importance of the topic}_

## Introduction
{Introduce the topic clearly and briefly. Explain why it's relevant, especially in the context of AUSTRAC, taxation, or compliance. Mention who the post is for (e.g., small businesses, accountants, etc.).}

## Key Concepts
- **{Concept 1}**: {Brief explanation}
- **{Concept 2}**: {Brief explanation}
- **{Concept 3}**: {Brief explanation}

## Real-World Implications
{Explain what happens if this is done incorrectly or ignored. Include examples of common pitfalls or legal/financial risks.}

## Compliance Checklist
Use this checklist to stay on the right side of regulations:
- [ ] {Requirement 1}
- [ ] {Requirement 2}
- [ ] {Best practice or tip}
- [ ] {Reporting or recordkeeping requirement}

## Practical Tips for Businesses
- **Automate where possible**: {e.g., use tools to streamline reporting}
- **Stay current**: {How to keep up with evolving laws}
- **Train your team**: {Why internal awareness matters}

## Case Example (Optional)
**Scenario**: {Brief fictional or anonymized real-world example}  
**Outcome**: {What went right/wrong and why}

## Final Thoughts
{Summarize key takeaways. Encourage compliance, and possibly suggest reviewing processes, tools, or seeking professional advice.}

## Additional Resources
- [AUSTRAC Official Website](https://www.austrac.gov.au)
- [ATO Compliance Resources](https://www.ato.gov.au)
- {Other useful links or guides}""",
                "category": InstructionCategory.RESPONSE_FORMATTING,
            },
        ]

        for output in outputs:
            obj, created = AgentExpectedOutput.objects.update_or_create(
                title=output["title"],
                user=user,
                defaults={
                    "expected_output": output["expected_output"],
                    "category": output["category"],
                    "is_enabled": True,
                    "is_global": True,
                },
            )
            self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Updated'}: {obj.title}"))
