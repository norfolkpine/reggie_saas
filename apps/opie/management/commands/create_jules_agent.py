from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.opie.models import Agent, ModelProvider, AgentInstruction, InstructionCategory

class Command(BaseCommand):
    help = 'Creates the Jules Code Agent.'

    def handle(self, *args, **options):
        self.stdout.write("Starting creation of Jules Code Agent...")

        User = get_user_model()

        # 1. Get or create a superuser to own the agent
        superuser, created = User.objects.get_or_create(
            email='jules.agent@example.com',
            defaults={
                'username': 'jules_agent',
                'is_superuser': True,
                'is_staff': True,
            }
        )
        if created:
            superuser.set_unusable_password()
            superuser.save()
            self.stdout.write(self.style.SUCCESS(f"Created superuser: {superuser.email}"))
        else:
            self.stdout.write(f"Found existing superuser: {superuser.email}")

        # 2. Find a suitable powerful model for the agent
        # We'll try to find a powerful model like GPT-4o, Claude 3 Opus, or fallback to the first available.
        model_candidates = ['gpt-4o', 'claude-3-opus-20240229']
        model = None
        for model_name in model_candidates:
            model = ModelProvider.objects.filter(model_name=model_name, is_enabled=True).first()
            if model:
                break

        if not model:
            model = ModelProvider.objects.filter(is_enabled=True).order_by('?').first()

        if not model:
            self.stdout.write(self.style.ERROR("No enabled ModelProvider found. Cannot create agent."))
            return

        self.stdout.write(f"Selected model for agent: {model.model_name}")

        # 3. Create the detailed instruction set for the agent
        instruction_text = """\
You are an expert programmer agent. Your purpose is to use the Jules API to perform coding tasks.

Workflow:
1.  **Clarify the Goal**: Understand the user's request for a code change.
2.  **List Sources**: Use the `list_jules_sources` tool to find the correct repository to work in. Show the user the available sources if they are unsure.
3.  **Start Session**: Once the source is confirmed, use the `start_jules_session` tool. The `prompt` should be a clear and detailed instruction for the Jules coding agent, and the `source` should be the full source name from the previous step.
4.  **Monitor Activity**: After starting a session, inform the user that the task has begun and that you will monitor the progress. Use the `get_jules_session_activity` tool with the `session_id` returned by `start_jules_session`. You may need to poll this endpoint multiple times.
5.  **Report Completion**: Once the activity stream shows the task is complete (e.g., a pull request is created), report the final result to the user.
"""
        instruction, created = AgentInstruction.objects.get_or_create(
            title="Jules Code Agent Instructions",
            defaults={
                'user': superuser,
                'instruction': instruction_text,
                'category': InstructionCategory.PROCESS,
                'is_global': True,
                'is_system': True,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Created new instruction set for Jules agent."))
        else:
            self.stdout.write("Found existing instruction set for Jules agent.")

        # 4. Create the Agent
        agent, created = Agent.objects.get_or_create(
            name="Jules Code Agent",
            defaults={
                'user': superuser,
                'description': "An agent that uses the Jules API to write and modify code.",
                'model': model,
                'instructions': instruction,
                'is_global': True,
                'default_reasoning': True,
                'search_knowledge': False,
            }
        )

        if created:
            self.stdout.write(self.style.SUCCESS("Successfully created the 'Jules Code Agent'."))
        else:
            self.stdout.write(self.style.WARNING("The 'Jules Code Agent' already exists."))

        self.stdout.write("To use the new agent, you may need to restart the application.")