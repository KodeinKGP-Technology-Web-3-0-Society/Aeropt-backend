import time
import logging
import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q
from django.contrib.auth import get_user_model

from roadmap.models import PathNode, NodeStatus, PathProgress
from users.supabase_sync import get_supabase_client, is_supabase_configured
from apis.cache_layer import invalidate_roadmap

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = "Background daemon that polls Supabase mastery_events and updates Django roadmap PathNodes."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=10, help="Polling interval in seconds")

    def handle(self, *args, **options):
        interval = options["interval"]
        self.stdout.write(self.style.SUCCESS(f"Starting mastery_events consumer (polling every {interval}s)..."))

        if not is_supabase_configured():
            self.stderr.write("Supabase is not configured. Exiting.")
            return

        client = get_supabase_client()
        if client is None:
            self.stderr.write("Failed to initialize Supabase client.")
            return

        # Start cursor from current time to avoid reprocessing historical events on start
        last_checked_at = timezone.now().isoformat()

        while True:
            try:
                self.poll_events(client, last_checked_at)
                # Update cursor to just before the loop ran to avoid missing overlapping events
                # Slight overlap is fine since updates are idempotent
                last_checked_at = (timezone.now() - datetime.timedelta(seconds=2)).isoformat()
            except Exception as e:
                logger.error("Error polling mastery_events: %s", e)
            
            time.sleep(interval)

    def poll_events(self, client, cutoff_time: str):
        res = (
            client.table("mastery_events")
            .select("*")
            .gte("created_at", cutoff_time)
            .order("created_at", desc=False)
            .execute()
        )
        events = res.data or []
        if not events:
            return

        for event in events:
            self.process_event(event)

    def process_event(self, event: dict):
        event_type = event.get("event_type")
        sid = event.get("user_id")
        concept_id = event.get("concept_id")
        new_score = event.get("new_score") or 0.0

        if event_type != "mastered":
            # For now, we only trigger roadmap unlocks on "mastered" events
            # "weak_flagged" could trigger remedial nodes, but not handled yet.
            return

        # Find the Django user
        user = User.objects.filter(Q(supabase_user_id=sid) | Q(id=sid)).first()
        if not user:
            logger.warning(f"Mastery event for unknown user {sid}")
            return

        # Find all pending/in_progress PathNodes for this concept
        nodes = PathNode.objects.filter(
            learning_path__user=user,
            concept_id=concept_id,
        ).exclude(status=NodeStatus.COMPLETED)

        for node in nodes:
            # Update the node to completed
            old_status = node.status
            node.proficiency_pct = int(new_score * 100)
            
            if node.proficiency_pct >= node.mastery_threshold:
                node.status = NodeStatus.COMPLETED
                node.completed_at = timezone.now()
                node.save(update_fields=["status", "proficiency_pct", "completed_at"])
                
                PathProgress.objects.create(
                    user=user,
                    path_node=node,
                    status=NodeStatus.COMPLETED,
                    proficiency_pct=node.proficiency_pct,
                    note="Auto-completed via Supabase mastery event"
                )
                
                # Trigger the auto-unlock logic (Step 27)
                from roadmap.engine import auto_unlock_nodes
                unlocked_count = auto_unlock_nodes(user)
                if unlocked_count > 0:
                    logger.info(f"Auto-unlocked {unlocked_count} new nodes for {user.email}")
                
                invalidate_roadmap(user)
                logger.info(f"User {user.email} mastered concept {concept_id}, completed PathNode {node.id}")
