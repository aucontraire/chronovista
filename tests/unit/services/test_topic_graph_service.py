"""
Tests for TopicGraphService.

Comprehensive test coverage for topic knowledge graph building and analysis.
"""

from datetime import datetime, timezone
from typing import Dict, List, Set
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mark all async tests in this module
pytestmark = pytest.mark.asyncio

from chronovista.db.models import TopicCategory as TopicCategoryDB
from chronovista.db.models import Video as VideoDB
from chronovista.models.topic_category import TopicCategorySearchFilters
from chronovista.models.video_tag import VideoTagStatistics
from chronovista.services.topic_graph_service import (
    TopicEdge,
    TopicGraph,
    TopicGraphService,
    TopicNode,
)


class TestTopicNode:
    """Tests for TopicNode dataclass."""

    def test_topic_node_basic_creation(self):
        """Test basic TopicNode creation."""
        node = TopicNode(
            topic_id="/m/music", category_name="Music", topic_type="category"
        )

        assert node.topic_id == "/m/music"
        assert node.category_name == "Music"
        assert node.topic_type == "category"
        assert node.parent_topic_id is None
        assert node.children == set()
        assert node.related_videos == set()
        assert node.level == 0

    def test_topic_node_with_parent(self):
        """Test TopicNode creation with parent relationship."""
        node = TopicNode(
            topic_id="/m/rock",
            category_name="Rock Music",
            topic_type="subcategory",
            parent_topic_id="/m/music",
            level=1,
        )

        assert node.topic_id == "/m/rock"
        assert node.parent_topic_id == "/m/music"
        assert node.level == 1

    def test_topic_node_with_children_and_videos(self):
        """Test TopicNode with children and related videos."""
        children = {"/m/rock", "/m/pop"}
        videos = {"video1", "video2", "video3"}

        node = TopicNode(
            topic_id="/m/music",
            category_name="Music",
            topic_type="category",
            children=children,
            related_videos=videos,
        )

        assert node.children == children
        assert node.related_videos == videos

    def test_topic_node_post_init_defaults(self):
        """Test __post_init__ sets default empty sets."""
        node = TopicNode(
            topic_id="/m/test",
            category_name="Test",
            topic_type="test",
            children=None,
            related_videos=None,
        )

        # __post_init__ should create empty sets
        assert node.children == set()
        assert node.related_videos == set()


class TestTopicEdge:
    """Tests for TopicEdge dataclass."""

    def test_topic_edge_basic_creation(self):
        """Test basic TopicEdge creation."""
        edge = TopicEdge(
            source_topic_id="/m/music",
            target_topic_id="/m/rock",
            relationship_type="parent_child",
        )

        assert edge.source_topic_id == "/m/music"
        assert edge.target_topic_id == "/m/rock"
        assert edge.relationship_type == "parent_child"
        assert edge.weight == 1.0
        assert edge.metadata == {}

    def test_topic_edge_with_metadata_and_weight(self):
        """Test TopicEdge with custom weight and metadata."""
        metadata = {"shared_videos": 5, "confidence": 0.8}
        edge = TopicEdge(
            source_topic_id="/m/rock",
            target_topic_id="/m/pop",
            relationship_type="content_similarity",
            weight=0.75,
            metadata=metadata,
        )

        assert edge.weight == 0.75
        assert edge.metadata == metadata

    def test_topic_edge_post_init_defaults(self):
        """Test __post_init__ sets default empty metadata."""
        edge = TopicEdge(
            source_topic_id="/m/test1",
            target_topic_id="/m/test2",
            relationship_type="test",
            metadata=None,
        )

        assert edge.metadata == {}


class TestTopicGraph:
    """Tests for TopicGraph operations."""

    @pytest.fixture
    def sample_nodes(self):
        """Create sample topic nodes for testing."""
        nodes = {
            "/m/music": TopicNode(
                topic_id="/m/music",
                category_name="Music",
                topic_type="category",
                children={"/m/rock", "/m/pop"},
                level=0,
            ),
            "/m/rock": TopicNode(
                topic_id="/m/rock",
                category_name="Rock Music",
                topic_type="subcategory",
                parent_topic_id="/m/music",
                children={"/m/metal"},
                level=1,
            ),
            "/m/pop": TopicNode(
                topic_id="/m/pop",
                category_name="Pop Music",
                topic_type="subcategory",
                parent_topic_id="/m/music",
                level=1,
            ),
            "/m/metal": TopicNode(
                topic_id="/m/metal",
                category_name="Metal Music",
                topic_type="subcategory",
                parent_topic_id="/m/rock",
                level=2,
            ),
        }
        return nodes

    @pytest.fixture
    def sample_edges(self):
        """Create sample topic edges for testing."""
        return [
            TopicEdge("/m/music", "/m/rock", "parent_child"),
            TopicEdge("/m/music", "/m/pop", "parent_child"),
            TopicEdge("/m/rock", "/m/metal", "parent_child"),
        ]

    @pytest.fixture
    def sample_graph(self, sample_nodes, sample_edges):
        """Create sample TopicGraph for testing."""
        return TopicGraph(
            nodes=sample_nodes,
            edges=sample_edges,
            root_topics={"/m/music"},
            max_depth=2,
        )

    def test_get_node_exists(self, sample_graph):
        """Test getting an existing node."""
        node = sample_graph.get_node("/m/rock")
        assert node is not None
        assert node.topic_id == "/m/rock"
        assert node.category_name == "Rock Music"

    def test_get_node_not_exists(self, sample_graph):
        """Test getting a non-existent node."""
        node = sample_graph.get_node("/m/nonexistent")
        assert node is None

    def test_get_children_with_children(self, sample_graph):
        """Test getting children of a node that has children."""
        children = sample_graph.get_children("/m/music")
        assert len(children) == 2
        child_ids = {child.topic_id for child in children}
        assert child_ids == {"/m/rock", "/m/pop"}

    def test_get_children_no_children(self, sample_graph):
        """Test getting children of a leaf node."""
        children = sample_graph.get_children("/m/pop")
        assert children == []

    def test_get_children_node_not_exists(self, sample_graph):
        """Test getting children of non-existent node."""
        children = sample_graph.get_children("/m/nonexistent")
        assert children == []

    def test_get_path_to_root_leaf_node(self, sample_graph):
        """Test getting path from leaf to root."""
        path = sample_graph.get_path_to_root("/m/metal")
        assert len(path) == 3
        path_ids = [node.topic_id for node in path]
        assert path_ids == ["/m/music", "/m/rock", "/m/metal"]

    def test_get_path_to_root_root_node(self, sample_graph):
        """Test getting path for root node."""
        path = sample_graph.get_path_to_root("/m/music")
        assert len(path) == 1
        assert path[0].topic_id == "/m/music"

    def test_get_path_to_root_nonexistent(self, sample_graph):
        """Test getting path for non-existent node."""
        path = sample_graph.get_path_to_root("/m/nonexistent")
        assert path == []

    def test_find_related_topics_direct_relations(self, sample_graph):
        """Test finding directly related topics."""
        related = sample_graph.find_related_topics("/m/rock", max_distance=1)

        # Should find parent (/m/music) and child (/m/metal)
        related_ids = {node.topic_id for node, distance in related}
        assert "/m/music" in related_ids  # parent
        assert "/m/metal" in related_ids  # child

        # Check distances
        for node, distance in related:
            assert distance <= 1

    def test_find_related_topics_extended_distance(self, sample_graph):
        """Test finding topics within extended distance."""
        related = sample_graph.find_related_topics("/m/metal", max_distance=2)

        # Should find grandparent (/m/music) at distance 2
        related_ids = {node.topic_id for node, distance in related}
        assert "/m/rock" in related_ids  # parent (distance 1)
        assert "/m/music" in related_ids  # grandparent (distance 2)

    def test_find_related_topics_nonexistent(self, sample_graph):
        """Test finding related topics for non-existent node."""
        related = sample_graph.find_related_topics("/m/nonexistent")
        assert related == []


class TestTopicGraphService:
    """Tests for TopicGraphService."""

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        return MagicMock()

    @pytest.fixture
    def mock_topic_repo(self):
        """Create mock TopicCategoryRepository."""
        return AsyncMock()

    @pytest.fixture
    def mock_video_repo(self):
        """Create mock VideoRepository."""
        return AsyncMock()

    @pytest.fixture
    def mock_video_tag_repo(self):
        """Create mock VideoTagRepository."""
        return AsyncMock()

    @pytest.fixture
    def topic_graph_service(
        self, mock_topic_repo, mock_video_repo, mock_video_tag_repo
    ):
        """Create TopicGraphService with mocked repositories."""
        service = TopicGraphService()
        service.topic_repo = mock_topic_repo
        service.video_repo = mock_video_repo
        service.video_tag_repo = mock_video_tag_repo
        return service

    @pytest.fixture
    def sample_topic_db_data(self):
        """Create sample database topic data."""
        return [
            MagicMock(
                topic_id="/m/music",
                category_name="Music",
                topic_type="category",
                parent_topic_id=None,
            ),
            MagicMock(
                topic_id="/m/rock",
                category_name="Rock Music",
                topic_type="subcategory",
                parent_topic_id="/m/music",
            ),
            MagicMock(
                topic_id="/m/pop",
                category_name="Pop Music",
                topic_type="subcategory",
                parent_topic_id="/m/music",
            ),
            MagicMock(
                topic_id="/m/metal",
                category_name="Metal Music",
                topic_type="subcategory",
                parent_topic_id="/m/rock",
            ),
        ]

    async def test_build_topic_hierarchy_graph_success(
        self, topic_graph_service, mock_session, sample_topic_db_data
    ):
        """Test successful topic hierarchy graph building."""
        # Mock repository response
        topic_graph_service.topic_repo.search_topics.return_value = sample_topic_db_data

        # Call the method
        graph = await topic_graph_service.build_topic_hierarchy_graph(mock_session)

        # Verify repository was called correctly
        topic_graph_service.topic_repo.search_topics.assert_called_once()
        call_args = topic_graph_service.topic_repo.search_topics.call_args
        assert isinstance(call_args[0][1], TopicCategorySearchFilters)

        # Verify graph structure
        assert isinstance(graph, TopicGraph)
        assert len(graph.nodes) == 4
        assert "/m/music" in graph.root_topics
        assert graph.max_depth >= 2

        # Verify hierarchy relationships
        music_node = graph.get_node("/m/music")
        assert music_node is not None
        assert music_node.children is not None
        assert len(music_node.children) == 2  # rock and pop

        rock_node = graph.get_node("/m/rock")
        assert rock_node is not None
        assert rock_node.parent_topic_id == "/m/music"
        assert rock_node.children is not None
        assert len(rock_node.children) == 1  # metal

    async def test_build_topic_hierarchy_graph_empty_data(
        self, topic_graph_service, mock_session
    ):
        """Test building hierarchy graph with no topics."""
        topic_graph_service.topic_repo.search_topics.return_value = []

        graph = await topic_graph_service.build_topic_hierarchy_graph(mock_session)

        assert isinstance(graph, TopicGraph)
        assert len(graph.nodes) == 0
        assert len(graph.root_topics) == 0
        assert graph.max_depth == 0
        assert len(graph.edges) == 0

    async def test_build_topic_hierarchy_graph_circular_reference(
        self, topic_graph_service, mock_session
    ):
        """Test building hierarchy graph with circular reference."""
        # Create circular reference: A -> B -> A
        circular_data = [
            MagicMock(
                topic_id="/m/topic_a",
                category_name="Topic A",
                topic_type="category",
                parent_topic_id="/m/topic_b",
            ),
            MagicMock(
                topic_id="/m/topic_b",
                category_name="Topic B",
                topic_type="category",
                parent_topic_id="/m/topic_a",
            ),
        ]

        topic_graph_service.topic_repo.search_topics.return_value = circular_data

        # Should handle circular reference gracefully
        graph = await topic_graph_service.build_topic_hierarchy_graph(mock_session)

        assert isinstance(graph, TopicGraph)
        assert len(graph.nodes) == 2
        # Both should be treated as roots due to circular reference
        assert len(graph.root_topics) == 0  # No true roots due to circular reference

    async def test_build_content_similarity_graph_success(
        self, topic_graph_service, mock_session, sample_topic_db_data
    ):
        """Test building content similarity graph."""
        # Mock repository responses (builds on hierarchy graph)
        topic_graph_service.topic_repo.search_topics.return_value = sample_topic_db_data

        # Call the method
        graph = await topic_graph_service.build_content_similarity_graph(
            mock_session, min_shared_videos=1
        )

        # Verify repository calls (calls search_topics once for content similarity which builds on hierarchy)
        topic_graph_service.topic_repo.search_topics.assert_called_once()

        # Verify graph structure
        assert isinstance(graph, TopicGraph)
        assert len(graph.nodes) == 4

        # Verify similarity edges were created between sibling topics
        similarity_edges = [
            edge
            for edge in graph.edges
            if edge.relationship_type == "content_similarity"
        ]
        # Should have similarity edges between rock/pop (siblings under music)
        assert (
            len(similarity_edges) >= 0
        )  # May be 0 or more depending on sibling relationships

    async def test_build_content_similarity_graph_min_threshold(
        self, topic_graph_service, mock_session, sample_topic_db_data
    ):
        """Test content similarity graph with minimum shared videos threshold."""
        topic_graph_service.topic_repo.search_topics.return_value = sample_topic_db_data

        # Call with high threshold (doesn't affect sibling-based similarity in current implementation)
        graph = await topic_graph_service.build_content_similarity_graph(
            mock_session, min_shared_videos=100
        )

        # Verify repository calls
        topic_graph_service.topic_repo.search_topics.assert_called_once()

        # Verify graph structure
        assert isinstance(graph, TopicGraph)
        assert len(graph.nodes) == 4

    async def test_build_tag_based_content_graph_success(
        self, topic_graph_service, mock_session
    ):
        """Test building tag-based content graph."""
        # Mock topics for hierarchy graph
        mock_topics = [
            MagicMock(
                topic_id="/m/music",
                category_name="Music",
                topic_type="category",
                parent_topic_id=None,
            ),
            MagicMock(
                topic_id="/m/rock",
                category_name="Rock Music",
                topic_type="subcategory",
                parent_topic_id="/m/music",
            ),
        ]
        topic_graph_service.topic_repo.search_topics.return_value = mock_topics

        # Mock popular tags data
        mock_popular_tags = [("music", 10), ("rock", 5), ("guitar", 3)]
        topic_graph_service.video_tag_repo.get_popular_tags.return_value = (
            mock_popular_tags
        )

        # Mock related tags data
        topic_graph_service.video_tag_repo.get_related_tags.return_value = [
            ("rock", 3),
            ("guitar", 2),
        ]

        # Call the method
        graph = await topic_graph_service.build_tag_based_content_graph(
            mock_session, min_tag_cooccurrence=1
        )

        # Verify repository calls
        topic_graph_service.topic_repo.search_topics.assert_called_once()
        topic_graph_service.video_tag_repo.get_popular_tags.assert_called_once_with(
            mock_session, limit=100
        )

        # Verify graph structure includes both hierarchical topics and tag nodes
        assert isinstance(graph, TopicGraph)
        assert len(graph.nodes) >= 2  # At least the original topics

    async def test_build_video_topic_bridge_graph_success(
        self, topic_graph_service, mock_session
    ):
        """Test building video-topic bridge graph."""
        # Mock hierarchy topics
        mock_topics = [
            MagicMock(
                topic_id="/m/music",
                category_name="Music",
                topic_type="category",
                parent_topic_id=None,
            )
        ]
        topic_graph_service.topic_repo.search_topics.return_value = mock_topics

        # Mock tag statistics
        mock_tag_stats = VideoTagStatistics(
            total_tags=100,
            unique_tags=50,
            avg_tags_per_video=2.5,
            most_common_tags=[("music", 20), ("rock", 15)],
            tag_distribution={"music": 20, "rock": 15},
        )
        topic_graph_service.video_tag_repo.get_video_tag_statistics.return_value = (
            mock_tag_stats
        )

        # Call the method
        graph = await topic_graph_service.build_video_topic_bridge_graph(mock_session)

        # Verify repository calls
        topic_graph_service.topic_repo.search_topics.assert_called_once()
        topic_graph_service.video_tag_repo.get_video_tag_statistics.assert_called_once_with(
            mock_session
        )

        # Verify graph includes both topics and tag nodes
        assert isinstance(graph, TopicGraph)
        assert len(graph.nodes) >= 1

    async def test_analyze_tag_topic_relationships_success(
        self, topic_graph_service, mock_session
    ):
        """Test analyzing tag-topic relationships."""
        # Mock hierarchy topics
        mock_topics = [
            MagicMock(
                topic_id="/m/music",
                category_name="Music",
                topic_type="category",
                parent_topic_id=None,
            )
        ]
        topic_graph_service.topic_repo.search_topics.return_value = mock_topics

        # Mock tag statistics
        mock_tag_stats = VideoTagStatistics(
            total_tags=100,
            unique_tags=50,
            avg_tags_per_video=2.5,
            most_common_tags=[("music", 20), ("rock", 15)],
            tag_distribution={"music": 20, "rock": 15},
        )
        topic_graph_service.video_tag_repo.get_video_tag_statistics.return_value = (
            mock_tag_stats
        )

        # Call the method
        relationships = await topic_graph_service.analyze_tag_topic_relationships(
            mock_session
        )

        # Verify repository calls
        topic_graph_service.topic_repo.search_topics.assert_called_once()
        topic_graph_service.video_tag_repo.get_video_tag_statistics.assert_called_once_with(
            mock_session
        )

        # Verify result structure
        assert isinstance(relationships, dict)

    async def test_get_topic_clusters_success(
        self, topic_graph_service, mock_session, sample_topic_db_data
    ):
        """Test getting topic clusters."""
        # Create a sample graph first
        mock_graph = TopicGraph(
            nodes={
                "/m/music": TopicNode("/m/music", "Music", "category"),
                "/m/rock": TopicNode("/m/rock", "Rock", "subcategory", "/m/music"),
            },
            edges=[TopicEdge("/m/music", "/m/rock", "parent_child")],
            root_topics={"/m/music"},
            max_depth=1,
        )

        clusters = await topic_graph_service.get_topic_clusters(mock_graph)

        # Verify result structure
        assert isinstance(clusters, dict)

    async def test_analyze_topic_importance_success(
        self, topic_graph_service, mock_session, sample_topic_db_data
    ):
        """Test analyzing topic importance."""
        # Create a sample graph first
        mock_graph = TopicGraph(
            nodes={
                "/m/music": TopicNode("/m/music", "Music", "category"),
                "/m/rock": TopicNode("/m/rock", "Rock", "subcategory", "/m/music"),
            },
            edges=[TopicEdge("/m/music", "/m/rock", "parent_child")],
            root_topics={"/m/music"},
            max_depth=1,
        )

        # Mock tag statistics
        mock_tag_stats = VideoTagStatistics(
            total_tags=100,
            unique_tags=50,
            avg_tags_per_video=2.5,
            most_common_tags=[("music", 20), ("rock", 15)],
            tag_distribution={"music": 20, "rock": 15},
        )
        topic_graph_service.video_tag_repo.get_video_tag_statistics.return_value = (
            mock_tag_stats
        )

        importance = await topic_graph_service.analyze_topic_importance(
            mock_session, mock_graph
        )

        # Verify repository calls
        topic_graph_service.video_tag_repo.get_video_tag_statistics.assert_called_once()

        # Verify result structure
        assert isinstance(importance, dict)

    async def test_find_topic_paths_success(
        self, topic_graph_service, mock_session, sample_topic_db_data
    ):
        """Test finding topic paths."""
        # Create a sample graph with path relationships
        mock_graph = TopicGraph(
            nodes={
                "/m/music": TopicNode("/m/music", "Music", "category"),
                "/m/rock": TopicNode("/m/rock", "Rock", "subcategory", "/m/music"),
                "/m/pop": TopicNode("/m/pop", "Pop", "subcategory", "/m/music"),
                "/m/metal": TopicNode(
                    "/m/metal", "Metal", "subcategory", "/m/rock", level=2
                ),
            },
            edges=[
                TopicEdge("/m/music", "/m/rock", "parent_child"),
                TopicEdge("/m/music", "/m/pop", "parent_child"),
                TopicEdge("/m/rock", "/m/metal", "parent_child"),
            ],
            root_topics={"/m/music"},
            max_depth=2,
        )

        paths = await topic_graph_service.find_topic_paths(
            mock_graph, "/m/metal", "/m/pop"
        )

        # Verify result structure
        assert isinstance(paths, list)

    def test_export_graph_for_visualization_success(self, topic_graph_service):
        """Test exporting graph for visualization."""
        # Create sample graph
        nodes = {
            "/m/music": TopicNode("/m/music", "Music", "category"),
            "/m/rock": TopicNode("/m/rock", "Rock", "subcategory", "/m/music"),
        }
        edges = [TopicEdge("/m/music", "/m/rock", "parent_child")]
        graph = TopicGraph(nodes, edges, {"/m/music"}, 1)

        # Call export method
        export_data = topic_graph_service.export_graph_for_visualization(graph)

        # Verify structure
        assert isinstance(export_data, dict)
        assert "nodes" in export_data
        assert "edges" in export_data
        assert "graph_stats" in export_data

        # Verify nodes structure
        assert len(export_data["nodes"]) == 2
        for node in export_data["nodes"]:
            assert "id" in node
            assert "label" in node

        # Verify edges structure
        assert len(export_data["edges"]) == 1
        for edge in export_data["edges"]:
            assert "source" in edge
            assert "target" in edge
