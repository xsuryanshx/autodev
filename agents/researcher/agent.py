"""Research Agent - researches errors and provides solutions."""
from typing import Dict, Any, Optional, List
from utils.logger import get_logger
import json


class ResearcherAgent:
    """
    Researcher Agent responsibilities:
    - When subtask fails repeatedly
    - Web search for solutions
    - Deep research on errors
    - Feed learnings back to coder
    
    Skills:
    - Tavily search
    - Web browsing
    - Error analysis
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.logger = get_logger("autodev.researcher")
    
    def research_error(
        self,
        error: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Research an error and provide potential solutions.
        
        Args:
            error: The error message to research
            context: Additional context (language, framework, etc.)
            
        Returns:
            Dict with research findings and recommended fix
        """
        self.logger.info(f"Researching error: {error[:100]}...")
        
        # Extract key terms from error
        query = self._build_search_query(error, context)
        
        # Search the web using available tools
        search_results = self._search_web(query)
        
        # Analyze and synthesize findings
        findings = self._analyze_results(search_results)
        
        # Generate recommended fix
        recommended_fix = self._generate_fix(findings, error)
        
        result = {
            "query": query,
            "findings": findings,
            "recommended_fix": recommended_fix,
            "confidence": self._calculate_confidence(findings)
        }
        
        self.logger.info(f"Research complete. Confidence: {result['confidence']:.2f}")
        return result
    
    def _build_search_query(self, error: str, context: Optional[Dict[str, Any]]) -> str:
        """Build a search query from error message."""
        import re
        
        # Clean up error message
        error = error.strip()
        
        # Remove file paths and line numbers
        error = re.sub(r'[/\\]\S+:\d+', '', error)
        
        # Remove traceback markers
        error = re.sub(r'Traceback \(most recent call last\)', '', error)
        
        # Extract key error type
        error_type_match = re.search(r'(\w+Error|\w+Exception):', error)
        if error_type_match:
            error_type = error_type_match.group(1)
        else:
            error_type = ""
        
        # Get first meaningful line
        lines = [l.strip() for l in error.split('\n') if l.strip() and not l.strip().startswith('File')]
        first_line = lines[0] if lines else error[:50]
        
        # Build query with context
        lang = context.get("language", "") if context else ""
        framework = context.get("framework", "") if context else ""
        
        parts = [error_type, first_line[:50], lang, framework]
        query = ' '.join([p for p in parts if p])
        
        return query
    
    def _search_web(self, query: str) -> List[Dict[str, Any]]:
        """Search the web for solutions using web_search."""
        try:
            # Try using web_search from tools
            from web_search import web_search
            results = web_search(
                query=query,
                count=5,
                freshness="pm"  # Past month
            )
            return results
        except ImportError:
            self.logger.warning("web_search not available, using empty results")
            return []
        except Exception as e:
            self.logger.error(f"Search failed: {e}")
            return []
    
    def _analyze_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Analyze search results and extract relevant solutions."""
        findings = []
        
        for result in results:
            # Extract title and snippet
            title = result.get("title", "")
            snippet = result.get("snippet", "")
            url = result.get("url", "")
            
            # Determine relevance (simple heuristic)
            relevance = 0.5
            if "solution" in title.lower() or "fix" in title.lower():
                relevance += 0.2
            if "stackoverflow" in url.lower():
                relevance += 0.1
            
            findings.append({
                "title": title,
                "snippet": snippet,
                "url": url,
                "relevance": min(relevance, 1.0)
            })
        
        # Sort by relevance
        findings.sort(key=lambda x: x["relevance"], reverse=True)
        
        return findings
    
    def _generate_fix(self, findings: List[Dict[str, Any]], original_error: str) -> str:
        """Generate a recommended fix based on findings."""
        if not findings:
            return "No solutions found. Manual investigation required."
        
        # Use the top result
        top = findings[0]
        
        fix = f"Based on research:\n\n"
        fix += f"**Source:** {top.get('title')}\n"
        fix += f"**URL:** {top.get('url')}\n\n"
        fix += f"**Suggested approach:**\n{top.get('snippet', 'See source for details')}"
        
        return fix
    
    def _calculate_confidence(self, findings: List[Dict[str, Any]]) -> float:
        """Calculate confidence score for the research."""
        if not findings:
            return 0.0
        
        # Average relevance of top 3 findings
        top_n = findings[:3]
        avg_relevance = sum(f["relevance"] for f in top_n) / len(top_n)
        
        # Boost if we have multiple relevant results
        relevant_count = sum(1 for f in findings if f["relevance"] > 0.5)
        boost = min(relevant_count * 0.1, 0.2)
        
        return min(avg_relevance + boost, 1.0)
    
    def deep_research(
        self,
        topic: str,
        max_results: int = 10
    ) -> Dict[str, Any]:
        """
        Perform deep research on a topic.
        
        Args:
            topic: Topic to research
            max_results: Maximum number of results
            
        Returns:
            Comprehensive research findings
        """
        self.logger.info(f"Deep researching: {topic}")
        
        # Multiple searches with different queries
        queries = [
            topic,
            f"{topic} tutorial",
            f"{topic} best practices",
            f"{topic} common problems"
        ]
        
        all_results = []
        for query in queries:
            try:
                results = self._search_web(query)
                all_results.extend(results)
            except Exception:
                pass
        
        # Deduplicate and rank
        seen_urls = set()
        unique_results = []
        for r in all_results:
            url = r.get("url", "")
            if url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(r)
        
        return {
            "topic": topic,
            "findings": unique_results[:max_results],
            "summary": f"Found {len(unique_results)} relevant sources"
        }
