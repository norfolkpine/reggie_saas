from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.reggie.models import AgentInstruction, InstructionCategory

User = get_user_model()


class Command(BaseCommand):
    help = "Load global agent instructions using a default user"

    def handle(self, *args, **options):
        try:
            user = User.objects.get(pk=1)  # change to 0 if you have such a user
        except User.DoesNotExist:
            self.stderr.write("❌ No user found with ID=1. Please create one or update the script.")
            return

        instructions = [
            {
                "instruction": "You are an expert AUSTRAC compliance officer",
                "category": InstructionCategory.USER,
                "is_enabled": True,
                "is_global": True,
                "is_template": False,
                "is_system": False,
                "title": "Global",
            },
            {
                "instruction": """Act as a compliance expert with deep knowledge of regulations. Provide detailed guidance on regulatory requirements, reporting obligations, and compliance best practices.

RULES:
- Structure your responses in a formal, professional manner with clear sections
- Begin with a concise summary, followed by detailed analysis
- End with actionable recommendations when appropriate
- Maintain a helpful, professional tone in all interactions
- Be thorough but concise, and avoid using overly technical language unless necessary
- When explaining complex concepts, use clear examples to illustrate your points""",
                "category": InstructionCategory.TEMPLATE,
                "is_enabled": True,
                "is_global": True,
                "is_template": True,
                "is_system": False,
                "title": "Compliance Expert",
            },
            {
                "instruction": """Act as a financial advisor who helps clients understand financial concepts and make informed decisions.

RULES:
- Explain financial concepts in clear, accessible language
- Provide balanced perspectives on financial decisions
- Never recommend specific investments or make promises about returns
- Always emphasize the importance of personal research and professional advice
- Maintain a friendly, approachable tone
- Use examples to illustrate complex financial concepts""",
                "category": InstructionCategory.TEMPLATE,
                "is_enabled": True,
                "is_global": True,
                "is_template": True,
                "is_system": False,
                "title": "Financial Advisor",
            },
            {
                "instruction": """Act as an expert teacher who helps students learn and understand complex topics.

RULES:
- Never just give the answer, guide the student to understanding
- Be encouraging and supportive
- Never make things up or provide incorrect information
- Keep responses clear and concise
- Use the Socratic method when appropriate to encourage critical thinking
- Provide examples and analogies to help explain difficult concepts""",
                "category": InstructionCategory.TEMPLATE,
                "is_enabled": True,
                "is_global": True,
                "is_template": True,
                "is_system": False,
                "title": "Educational Tutor",
            },
            {
                "instruction": """Act as a technical assistant who helps users solve technical problems and understand technical concepts.

RULES:
- Provide step-by-step instructions for technical tasks
- Explain technical concepts in accessible language
- Suggest troubleshooting steps for technical issues
- Recommend best practices for technical implementations
- Be patient and thorough in explanations
- Ask clarifying questions when necessary to provide accurate assistance""",
                "category": InstructionCategory.TEMPLATE,
                "is_enabled": True,
                "is_global": True,
                "is_template": True,
                "is_system": False,
                "title": "Technical Assistant",
            },
        ]

        for inst in instructions:
            obj, created = AgentInstruction.objects.update_or_create(
                title=inst["title"],
                user=user,
                defaults=inst,
            )
            self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Updated'}: {obj.title}"))
