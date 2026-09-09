import logging
from django.utils import timezone
from roadmap.models import LearningPath, NodeStatus, PathProgress
from roadmap.syllabus import prerequisite_map

logger = logging.getLogger(__name__)

def auto_unlock_nodes(user) -> int:
    """
    Scans the user's active LearningPath for PENDING nodes.
    If a PENDING node has all of its prerequisites met (i.e. COMPLETED or SKIPPED),
    it is automatically unlocked (status -> IN_PROGRESS).
    
    Returns the number of newly unlocked nodes.
    """
    path = LearningPath.objects.filter(user=user, is_active=True).first()
    if not path:
        return 0
        
    pending_nodes = list(path.nodes.filter(status=NodeStatus.PENDING))
    if not pending_nodes:
        return 0
        
    prereqs = prerequisite_map()
    
    cleared_concepts = set(
        path.nodes.filter(status__in=[NodeStatus.COMPLETED, NodeStatus.SKIPPED])
        .values_list("concept_id", flat=True)
    )
    
    unlocked_count = 0
    
    for node in pending_nodes:
        node_prereqs = prereqs.get(node.concept_id, [])
        
        # If the node has prerequisites, check if ALL are met
        if node_prereqs:
            all_met = all(prereq in cleared_concepts for prereq in node_prereqs)
        else:
            # If no prerequisites, we unlock it only if the previous node in sequence is cleared
            # (To prevent unlocking the entire syllabus at once if prereqs are missing)
            if node.sequence_index == 0:
                all_met = True
            else:
                prev_node = path.nodes.filter(sequence_index=node.sequence_index - 1).first()
                all_met = prev_node and prev_node.status in [NodeStatus.COMPLETED, NodeStatus.SKIPPED]
                
        if all_met:
            node.status = NodeStatus.IN_PROGRESS
            node.started_at = timezone.now()
            node.save(update_fields=["status", "started_at"])
            
            PathProgress.objects.create(
                user=user,
                path_node=node,
                status=NodeStatus.IN_PROGRESS,
                note="Auto-unlocked because prerequisites are met"
            )
            unlocked_count += 1
            logger.info(f"Auto-unlocked PathNode {node.id} for user {user.email}")
            
    return unlocked_count
