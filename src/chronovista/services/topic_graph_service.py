"""
Topic Graph Service for Knowledge Graph Analysis.

Builds and analyzes graphs from YouTube knowledge graph topic IDs,
enabling discovery of content relationships and topic networks.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import TopicCategory as TopicCategoryDB
from chronovista.db.models import Video as VideoDB
from chronovista.models.topic_category import TopicCategorySearchFilters
from chronovista.repositories.topic_category_repository import TopicCategoryRepository
from chronovista.repositories.video_repository import VideoRepository
from chronovista.repositories.video_tag_repository import VideoTagRepository


@dataclass
class TopicNode:
    """Represents a topic node in the knowledge graph."""

    topic_id: str
    category_name: str
    topic_type: str
    parent_topic_id: Optional[str] = None
    children: Optional[Set[str]] = None
    related_videos: Optional[Set[str]] = None
    level: int = 0

    def __post_init__(self) -> None:
        if self.children is None:
            self.children = set()
        if self.related_videos is None:
            self.related_videos = set()


@dataclass
class TopicEdge:
    """Represents a relationship between topics."""

    source_topic_id: str
    target_topic_id: str
    relationship_type: str  # 'parent_child', 'content_similarity', 'co_occurrence'
    weight: float = 1.0
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}


@dataclass
class TopicGraph:
    """Complete topic knowledge graph with nodes and edges."""

    nodes: Dict[str, TopicNode]
    edges: List[TopicEdge]
    root_topics: Set[str]
    max_depth: int

    def get_node(self, topic_id: str) -> Optional[TopicNode]:
        """Get a topic node by ID."""
        return self.nodes.get(topic_id)

    def get_children(self, topic_id: str) -> List[TopicNode]:
        """Get all child nodes of a topic."""
        node = self.nodes.get(topic_id)
        if not node:
            return []
        return [
            self.nodes[child_id]
            for child_id in (node.children or set())
            if child_id in self.nodes
        ]

    def get_path_to_root(self, topic_id: str) -> List[TopicNode]:
        """Get the path from a topic to its root ancestor."""
        path: List[TopicNode] = []
        current_id: Optional[str] = topic_id

        while current_id and current_id in self.nodes:
            node = self.nodes[current_id]
            path.insert(0, node)  # Insert at beginning to build root-to-leaf path
            current_id = node.parent_topic_id

        return path

    def find_related_topics(
        self, topic_id: str, max_distance: int = 2
    ) -> List[Tuple[TopicNode, int]]:
        """Find topics related to the given topic within max_distance."""
        if topic_id not in self.nodes:
            return []

        visited = set()
        queue = [(topic_id, 0)]
        related = []

        while queue:
            current_id, distance = queue.pop(0)

            if current_id in visited or distance > max_distance:
                continue

            visited.add(current_id)
            node = self.nodes[current_id]

            if distance > 0:  # Don't include the starting topic
                related.append((node, distance))

            # Add parent and children to queue
            if node.parent_topic_id and node.parent_topic_id not in visited:
                queue.append((node.parent_topic_id, distance + 1))

            for child_id in node.children or set():
                if child_id not in visited:
                    queue.append((child_id, distance + 1))

        return related


class TopicGraphService:
    """Service for building and analyzing topic knowledge graphs."""

    def __init__(self) -> None:
        self.topic_repo = TopicCategoryRepository()
        self.video_repo = VideoRepository()
        self.video_tag_repo = VideoTagRepository()

    async def build_topic_hierarchy_graph(self, session: AsyncSession) -> TopicGraph:
        """Build a hierarchical topic graph from the database."""
        # Get all topics from database
        filters = TopicCategorySearchFilters()  # Get all topics
        all_topics = await self.topic_repo.search_topics(session, filters)

        # Build nodes
        nodes = {}
        root_topics = set()
        max_depth = 0

        for topic_db in all_topics:
            node = TopicNode(
                topic_id=topic_db.topic_id,
                category_name=topic_db.category_name,
                topic_type=topic_db.topic_type,
                parent_topic_id=topic_db.parent_topic_id,
            )
            nodes[topic_db.topic_id] = node

            if not topic_db.parent_topic_id:
                root_topics.add(topic_db.topic_id)

        # Build parent-child relationships and calculate levels
        for topic_id, node in nodes.items():
            if node.parent_topic_id and node.parent_topic_id in nodes:
                parent_node = nodes[node.parent_topic_id]
                if parent_node.children is None:
                    parent_node.children = set()
                parent_node.children.add(topic_id)

        # Calculate levels (depth from root)
        def calculate_level(topic_id: str, visited: Optional[Set[str]] = None) -> int:
            if visited is None:
                visited = set()

            if topic_id in visited:  # Circular reference
                return 0

            node = nodes.get(topic_id)
            if not node or not node.parent_topic_id:
                return 0

            visited.add(topic_id)
            level = 1 + calculate_level(node.parent_topic_id, visited)
            node.level = level
            return level

        for topic_id in nodes:
            level = calculate_level(topic_id)
            max_depth = max(max_depth, level)

        # Build hierarchical edges
        edges = []
        for node in nodes.values():
            if node.parent_topic_id and node.parent_topic_id in nodes:
                edge = TopicEdge(
                    source_topic_id=node.parent_topic_id,
                    target_topic_id=node.topic_id,
                    relationship_type="parent_child",
                    weight=1.0,
                    metadata={"hierarchy_level": node.level},
                )
                edges.append(edge)

        return TopicGraph(
            nodes=nodes, edges=edges, root_topics=root_topics, max_depth=max_depth
        )

    async def build_content_similarity_graph(
        self, session: AsyncSession, min_shared_videos: int = 2
    ) -> TopicGraph:
        """Build a graph based on content similarity (topics sharing videos)."""
        # First get the hierarchical graph as base
        graph = await self.build_topic_hierarchy_graph(session)

        # Get all videos with their topic associations
        # Note: This would require a VideoTopicCategory junction table in a full implementation
        # For now, we'll simulate this based on the existing schema

        # Group videos by topics (simulated - would need actual video-topic relationships)
        topic_video_map: Dict[str, Set[str]] = defaultdict(set)

        # In a real implementation, you'd have a query like:
        # SELECT topic_id, video_id FROM video_topic_categories
        # For now, we'll build content similarity edges based on existing hierarchical relationships

        # Calculate content similarity edges
        similarity_edges = []

        for topic_id, node in graph.nodes.items():
            # Find sibling topics (same parent) as potentially similar
            if node.parent_topic_id:
                parent_node = graph.nodes.get(node.parent_topic_id)
                if parent_node:
                    for sibling_id in parent_node.children or set():
                        if sibling_id != topic_id:
                            # Create similarity edge between siblings
                            edge = TopicEdge(
                                source_topic_id=topic_id,
                                target_topic_id=sibling_id,
                                relationship_type="content_similarity",
                                weight=0.7,  # Siblings are moderately similar
                                metadata={"similarity_basis": "shared_parent"},
                            )
                            similarity_edges.append(edge)

        # Add similarity edges to the graph
        graph.edges.extend(similarity_edges)

        return graph

    async def build_tag_based_content_graph(
        self, session: AsyncSession, min_tag_cooccurrence: int = 3
    ) -> TopicGraph:
        """Build a content similarity graph based on video tag relationships."""
        # Start with hierarchical graph as base
        graph = await self.build_topic_hierarchy_graph(session)
        
        # Get popular tags to focus on
        popular_tags = await self.video_tag_repo.get_popular_tags(session, limit=100)
        tag_names = [tag[0] for tag in popular_tags]
        
        if not tag_names:
            return graph
        
        # Build tag co-occurrence relationships
        tag_similarity_edges = []
        
        for i, tag_a in enumerate(tag_names):
            # Get related tags that frequently appear with tag_a
            related_tags = await self.video_tag_repo.get_related_tags(
                session, tag_a, limit=20
            )
            
            for tag_b, cooccurrence_count in related_tags:
                if cooccurrence_count >= min_tag_cooccurrence and tag_b in tag_names:
                    # Calculate similarity weight based on co-occurrence frequency
                    weight = min(1.0, cooccurrence_count / 50.0)  # Normalize to 0-1
                    
                    # Create content similarity edge
                    edge = TopicEdge(
                        source_topic_id=f"tag:{tag_a}",  # Use tag: prefix for tag-based topics
                        target_topic_id=f"tag:{tag_b}",
                        relationship_type="tag_cooccurrence",
                        weight=weight,
                        metadata={
                            "cooccurrence_count": cooccurrence_count,
                            "tag_a": tag_a,
                            "tag_b": tag_b,
                        },
                    )
                    tag_similarity_edges.append(edge)
        
        # Add tag-based nodes to the graph
        for tag_name, count in popular_tags:
            tag_node = TopicNode(
                topic_id=f"tag:{tag_name}",
                category_name=f"Tag: {tag_name}",
                topic_type="user_tag",
                parent_topic_id=None,
                children=set(),
                related_videos=set(),  # Would be populated with actual video IDs
                level=0,
            )
            graph.nodes[f"tag:{tag_name}"] = tag_node
        
        # Add tag similarity edges to the graph
        graph.edges.extend(tag_similarity_edges)
        
        return graph

    async def build_video_topic_bridge_graph(
        self, session: AsyncSession
    ) -> TopicGraph:
        """Build a graph that bridges formal topics with user-generated tags via videos."""
        # Start with hierarchical graph
        graph = await self.build_topic_hierarchy_graph(session)
        
        # Get video statistics for tag analytics
        tag_stats = await self.video_tag_repo.get_video_tag_statistics(session)
        
        # Add tag nodes to the graph
        for tag_name, count in tag_stats.most_common_tags:
            tag_node = TopicNode(
                topic_id=f"tag:{tag_name}",
                category_name=f"Tag: {tag_name}",
                topic_type="user_tag",
                parent_topic_id=None,
                children=set(),
                related_videos=set(),
                level=0,
            )
            graph.nodes[f"tag:{tag_name}"] = tag_node
        
        # Create bridge edges between formal topics and tags
        # This would require domain knowledge or ML to map topics to tags
        # For now, create simple heuristic mappings
        bridge_edges = []
        
        # Example heuristic: match topic category names with tag names
        for topic_id, topic_node in graph.nodes.items():
            if not topic_id.startswith("tag:"):  # Skip tag nodes
                topic_name_lower = topic_node.category_name.lower()
                
                for tag_name, _ in tag_stats.most_common_tags:
                    # Simple string matching - in practice you'd use more sophisticated methods
                    if (
                        tag_name.lower() in topic_name_lower
                        or topic_name_lower in tag_name.lower()
                    ):
                        # Create bridge edge
                        edge = TopicEdge(
                            source_topic_id=topic_id,
                            target_topic_id=f"tag:{tag_name}",
                            relationship_type="topic_tag_bridge",
                            weight=0.6,  # Moderate confidence in heuristic matching
                            metadata={
                                "matching_method": "string_similarity",
                                "topic_name": topic_node.category_name,
                                "tag_name": tag_name,
                            },
                        )
                        bridge_edges.append(edge)
        
        # Add bridge edges to the graph
        graph.edges.extend(bridge_edges)
        
        return graph

    async def analyze_tag_topic_relationships(
        self, session: AsyncSession
    ) -> Dict[str, Dict[str, float]]:
        """Analyze relationships between user tags and formal topic categories."""
        # Get tag statistics
        tag_stats = await self.video_tag_repo.get_video_tag_statistics(session)
        
        # Get all topics
        filters = TopicCategorySearchFilters()
        all_topics = await self.topic_repo.search_topics(session, filters)
        
        relationships: Dict[str, Dict[str, float]] = {}
        
        # For each tag, analyze its relationship with formal topics
        for tag_name, tag_count in tag_stats.most_common_tags:
            relationships[tag_name] = {}
            
            # Simple analysis based on name similarity
            for topic in all_topics:
                topic_name = topic.category_name.lower()
                tag_lower = tag_name.lower()
                
                # Calculate similarity score (simple implementation)
                similarity_score = 0.0
                
                # Exact match
                if tag_lower == topic_name:
                    similarity_score = 1.0
                # Substring match
                elif tag_lower in topic_name or topic_name in tag_lower:
                    similarity_score = 0.8
                # Word overlap
                else:
                    tag_words = set(tag_lower.split())
                    topic_words = set(topic_name.split())
                    overlap = len(tag_words.intersection(topic_words))
                    if overlap > 0:
                        similarity_score = overlap / max(len(tag_words), len(topic_words))
                
                if similarity_score > 0.3:  # Only include meaningful relationships
                    relationships[tag_name][topic.topic_id] = similarity_score
        
        return relationships

    async def get_topic_clusters(
        self, graph: TopicGraph, cluster_method: str = "hierarchical"
    ) -> Dict[str, List[str]]:
        """Group topics into clusters based on relationships."""
        clusters = {}

        if cluster_method == "hierarchical":
            # Cluster by root topic ancestry
            for root_id in graph.root_topics:
                cluster_topics = []

                def collect_descendants(topic_id: str) -> None:
                    cluster_topics.append(topic_id)
                    node = graph.nodes.get(topic_id)
                    if node:
                        for child_id in node.children or set():
                            collect_descendants(child_id)

                collect_descendants(root_id)

                root_node = graph.nodes.get(root_id)
                cluster_name = root_node.category_name if root_node else root_id
                clusters[cluster_name] = cluster_topics

        elif cluster_method == "content_similarity":
            # Use similarity edges to form clusters
            # This is a simplified approach - in practice you'd use graph clustering algorithms
            similarity_groups = defaultdict(set)

            for edge in graph.edges:
                if edge.relationship_type == "content_similarity":
                    group_key = min(edge.source_topic_id, edge.target_topic_id)
                    similarity_groups[group_key].add(edge.source_topic_id)
                    similarity_groups[group_key].add(edge.target_topic_id)

            for i, (key, topic_set) in enumerate(similarity_groups.items()):
                clusters[f"similarity_cluster_{i}"] = list(topic_set)

        return clusters

    async def analyze_topic_importance(
        self, session: AsyncSession, graph: TopicGraph
    ) -> Dict[str, float]:
        """Calculate importance scores for topics based on graph metrics and tag data."""
        importance_scores = {}
        
        # Get tag statistics for enhanced scoring
        tag_stats = await self.video_tag_repo.get_video_tag_statistics(session)
        tag_popularity = {tag: count for tag, count in tag_stats.most_common_tags}

        for topic_id, node in graph.nodes.items():
            score = 0.0

            # Hierarchy-based importance
            if not node.parent_topic_id:  # Root topics are important
                score += 1.0

            # Children count (topics with more children are more important)
            score += len(node.children or set()) * 0.3

            # Level-based importance (higher level = more specific, lower importance)
            score += max(0, (graph.max_depth - node.level)) * 0.2

            # Content association importance (more videos = more important)
            score += len(node.related_videos or set()) * 0.1
            
            # Tag-based importance for tag nodes
            if topic_id.startswith("tag:"):
                tag_name = topic_id[4:]  # Remove "tag:" prefix
                if tag_name in tag_popularity:
                    # Add tag popularity score (normalized)
                    max_tag_count = max(tag_popularity.values()) if tag_popularity else 1
                    normalized_popularity = tag_popularity[tag_name] / max_tag_count
                    score += normalized_popularity * 0.5
            
            # Edge-based importance (topics with more connections are more important)
            edge_count = sum(
                1 for edge in graph.edges 
                if edge.source_topic_id == topic_id or edge.target_topic_id == topic_id
            )
            score += edge_count * 0.1

            importance_scores[topic_id] = score

        return importance_scores

    async def find_topic_paths(
        self, graph: TopicGraph, source_topic_id: str, target_topic_id: str
    ) -> List[List[str]]:
        """Find all paths between two topics in the graph."""
        if source_topic_id not in graph.nodes or target_topic_id not in graph.nodes:
            return []

        def find_paths_recursive(
            current_id: str, target_id: str, path: List[str], visited: Set[str]
        ) -> List[List[str]]:
            if current_id == target_id:
                return [path + [current_id]]

            if current_id in visited:
                return []

            visited.add(current_id)
            all_paths = []

            current_node = graph.nodes[current_id]

            # Try parent path
            if (
                current_node.parent_topic_id
                and current_node.parent_topic_id not in visited
            ):
                paths = find_paths_recursive(
                    current_node.parent_topic_id,
                    target_id,
                    path + [current_id],
                    visited.copy(),
                )
                all_paths.extend(paths)

            # Try children paths
            for child_id in current_node.children or set():
                if child_id not in visited:
                    paths = find_paths_recursive(
                        child_id, target_id, path + [current_id], visited.copy()
                    )
                    all_paths.extend(paths)

            return all_paths

        return find_paths_recursive(source_topic_id, target_topic_id, [], set())

    def export_graph_for_visualization(self, graph: TopicGraph) -> Dict[str, Any]:
        """Export graph in a format suitable for visualization tools (D3.js, NetworkX, etc.)."""
        nodes_export = []
        edges_export = []

        # Export nodes
        for topic_id, node in graph.nodes.items():
            nodes_export.append(
                {
                    "id": topic_id,
                    "label": node.category_name,
                    "type": node.topic_type,
                    "level": node.level,
                    "children_count": len(node.children or set()),
                    "video_count": len(node.related_videos or set()),
                    "is_root": node.parent_topic_id is None,
                }
            )

        # Export edges
        for edge in graph.edges:
            edges_export.append(
                {
                    "source": edge.source_topic_id,
                    "target": edge.target_topic_id,
                    "type": edge.relationship_type,
                    "weight": edge.weight,
                    "metadata": edge.metadata,
                }
            )

        return {
            "nodes": nodes_export,
            "edges": edges_export,
            "graph_stats": {
                "total_nodes": len(graph.nodes),
                "total_edges": len(graph.edges),
                "root_topics": len(graph.root_topics),
                "max_depth": graph.max_depth,
            },
        }
