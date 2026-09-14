"""
analytics/signals.py
====================
Signals implementation.
"""

from django.dispatch import receiver
from chatbot.signals import concept_mentioned

@receiver(concept_mentioned)
def on_concept_mentioned(sender, user, concepts_data, **kwargs):
    pass
