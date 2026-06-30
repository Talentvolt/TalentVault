import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class TableDetector:
    """
    TableDetector classifies extracted document tables into domain categories:
    - education (e.g. degrees, GPAs, graduation years)
    - experience (e.g. roles, companies, projects)
    - certification (e.g. credentials, certification bodies)
    - skills (e.g. skill matrix, proficiency levels)
    - other (default / fallback)
    """

    # Scoring keywords for classification
    KEYWORDS_MAP = {
        "education": {
            "degree", "gpa", "cgpa", "university", "college", "school", "major",
            "graduation", "education", "percentage", "marks", "grade", "academic",
            "passing year", "institution", "course", "ssc", "hsc"
        },
        "experience": {
            "company", "designation", "role", "experience", "responsibilities",
            "duration", "employment", "job title", "project", "work", "responsibilities",
            "key results", "client", "position"
        },
        "certification": {
            "certification", "credential", "license", "certificate", "issued",
            "expiry", "authority", "validity", "accredited", "credential id"
        },
        "skills": {
            "skill", "proficiency", "expertise", "technology", "programming",
            "tools", "framework", "database", "operating system", "level", "competency"
        }
    }

    def detect_table_category(self, rows: List[List[str]]) -> str:
        """
        Classifies a table by scoring the occurrences of keywords in its cell texts.
        Returns:
            str: "education", "experience", "certification", "skills", or "other"
        """
        if not rows:
            return "other"

        # Flatten and normalize cell texts
        flat_text = " ".join(str(cell) for row in rows for cell in row).lower()
        
        scores = {}
        for category, keywords in self.KEYWORDS_MAP.items():
            score = 0
            for kw in keywords:
                # Count keyword matches as whole words or substring checks where appropriate
                if kw in flat_text:
                    score += 1
            scores[category] = score

        logger.debug(f"Table classification scores: {scores}")

        # Determine highest scoring category
        max_score = 0
        best_category = "other"
        for category, score in scores.items():
            if score > max_score:
                max_score = score
                best_category = category

        # Return category if it meets a minimum score threshold of 1
        if max_score >= 1:
            return best_category
        return "other"
