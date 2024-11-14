from abc import ABC, abstractmethod
import requests
from bs4 import BeautifulSoup
from jobs.models import Job, Requested
import time
import logging
from typing import Dict, Any, Optional
from django.db import transaction
from jobs.summarizer import summarize_text

class WebScraper(ABC):
    """Base scraper class for job websites."""
    
    def __init__(self, base_url: str, filter_url: str, request_limit: int):
        self.base_url = base_url
        self.filter_url = filter_url
        self.logger = logging.getLogger(f'scraper.{self.__class__.__name__}')
        self.request_limit = request_limit
        self.request_count = 0

    # Main Flow Methods
    # --------------------------------------------------
    def run(self) -> int:
        """Main entry point for the scraper."""
        try:
            html = self.get_main_html()
            job_listings = self.get_job_listings(html)
            jobs_data = self.process_job_listings(job_listings)
            return self.save_jobs(jobs_data)
        except Exception as e:
            self.logger.error(f"Error in scraping process: {e}")
            return 0

    def get_main_html(self) -> str:
        """Fetches HTML from the main job listings page."""
        res = requests.get(self.filter_url)
        res.raise_for_status()
        return res.text

    def get_job_listings(self, html: str) -> Dict[str, Dict[str, str]]:
        """Extracts basic job information (title, link) from the main listings page."""
        soup = BeautifulSoup(html, 'html.parser')
        containers = soup.find_all(**self.get_jobs_container_selector())
        
        if not containers:
            self.logger.warning("No job listings found on the page")
            return {}
        
        return self._extract_listings_from_containers(containers)

    def _extract_listings_from_containers(self, containers) -> Dict[str, Dict[str, str]]:
        """Processes each container to extract job listings."""
        all_listings = {}
        for container in containers:
            try:
                for listing in container.find_all(**self.get_listings_selector()):
                    title_element = listing.find(**self.get_listing_title_selector())
                    if title_element and (title := title_element.find(text=True, recursive=False)):
                        link = self.extract_job_link(listing)
                        all_listings[title.strip()] = {"link": link}
            except Exception as e:
                self.logger.error(f"Error processing container: {e}")
        return all_listings

    # Job Details Processing
    # --------------------------------------------------
    def process_job_listings(self, listings: Dict) -> Dict:
        """Processes each job listing to get detailed information."""
        detailed_jobs = {}
        for title, data in listings.items():
            if job_details := self._process_single_job(title, data["link"]):
                detailed_jobs[title] = job_details
        return detailed_jobs

    def _process_single_job(self, title: str, link: str) -> Optional[Dict]:
        """Processes a single job listing."""
        try:
            if Job.objects.filter(url=link).exists():
                return None
            
            if soup := self._get_job_page(link, title):
                experience = self.extract_experience_level(soup)
                return {
                    "company": self.extract_company(soup),
                    "location": self.extract_location(soup),
                    "operating_mode": self.extract_operating_mode(soup),
                    "experience": experience,
                    "salary": self.extract_salary(soup),
                    "description": self.extract_description(soup),
                    "skills": self.process_skills(soup, experience),
                    "link": link
                }
        except Exception as e:
            self.logger.error(f"Error processing job {title}: {e}")
        return None

    def _get_job_page(self, link: str, title: str) -> Optional[BeautifulSoup]:
        """Fetches and parses individual job posting page with request limit."""
        if self.request_count >= self.request_limit:
            return None
        
        if Requested.objects.filter(url=link).exists():
            return None
        
        try:
            headers = {
                'User-Agent': "Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0"
            }
            response = requests.get(link, headers=headers)
            self.request_count += 1
            time.sleep(1)
            
            Requested.objects.create(url=link, title=title)
            self.logger.info(f"Requested: {title}")
            
            return BeautifulSoup(response.text, "html.parser")
        except requests.RequestException as e:
            self.logger.error(f"Failed to request {title}: {e}")
            return None

    # Skills Processing
    # --------------------------------------------------
    def process_skills(self, soup: BeautifulSoup, experience: str) -> Dict[str, str]:
        """Main method for processing skills based on job type."""
        if self.has_skill_sections():
            return self._process_sectioned_skills(soup, experience)
        return self._process_single_container_skills(soup)

    def _process_sectioned_skills(self, soup: BeautifulSoup, experience: str) -> Dict[str, str]:
        """Processes skills that are divided into required and nice-to-have sections."""
        skills = {}
        if container := soup.find(**self.get_skills_container_selector()):
            self._extract_required_skills(container, skills, experience)
            self._extract_nice_to_have_skills(container, skills)
        return skills

    def _extract_required_skills(self, container: BeautifulSoup, skills: Dict[str, str], experience: str):
        """Extracts required skills with experience-based levels."""
        if required := container.find(**self.get_required_skills_selector()):
            try:
                for skill in required.find_all(**self.get_skill_item_selector()):
                    if skill_name := skill.find("span"):
                        skills[skill_name.text.strip()] = self.get_standardized_skill_level(experience)
            except Exception as e:
                self.logger.error(f"Error processing required skills: {e}")

    def _extract_nice_to_have_skills(self, container: BeautifulSoup, skills: Dict[str, str]):
        """Extracts nice-to-have skills."""
        if nice := container.find(**self.get_nice_skills_selector()):
            try:
                for skill in nice.find_all(**self.get_skill_item_selector()):
                    if skill_name := skill.find("span"):
                        skills[skill_name.text.strip()] = "nice to have"
            except Exception as e:
                self.logger.error(f"Error processing nice-to-have skills: {e}")

    def _process_single_container_skills(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Processes skills from a single container (no sections)."""
        skills = {}
        if container := soup.find(**self.get_skills_container_selector()):
            for element in container.find_all(**self.get_skill_item_selector()):
                if (name := self.extract_skill_name(element)) and (level := self.extract_skill_level(element)):
                    skills[name] = level
        return skills

    def get_standardized_skill_level(self, experience: str) -> str:
        """Standardizes skill levels based on experience."""
        experience = experience.lower()
        if not experience:
            return 'regular'
        
        if any(level in experience for level in ['senior', 'lead', 'expert', 'principal']):
            return 'senior'
        elif any(level in experience for level in ['mid', 'regular', 'intermediate']):
            return 'regular'
        elif any(level in experience for level in ['junior', 'intern', 'trainee', 'entry']):
            return 'junior'
        return 'regular'

    # Database Operations
    # --------------------------------------------------
    @transaction.atomic
    def save_jobs(self, jobs_data: Dict) -> int:
        """Saves processed jobs to the database."""
        saved_count = 0
        for title, data in jobs_data.items():
            try:
                description = data.get("description", "")
                summary = summarize_text(description) if description else ""
                
                if not self._is_duplicate_job(title, data):
                    Job.objects.create(
                        title=title,
                        company=data.get("company"),
                        location=data.get("location"),
                        operating_mode=data.get("operating_mode"),
                        experience=data.get("experience"),
                        salary=data.get("salary"),
                        description=description,
                        skills=data.get("skills"),
                        summary=summary,
                        url=data.get("link")
                    )
                    saved_count += 1
                    self.logger.info(f"Created job: {title}")
            except Exception as e:
                self.logger.error(f"Error saving job {title}: {e}")
        return saved_count

    def _is_duplicate_job(self, title: str, data: Dict) -> bool:
        """Checks if a job already exists in the database."""
        return (
            Job.objects.filter(url=data.get("link")).exists() or
            Job.objects.filter(
                title__iexact=title,
                company__iexact=data.get("company")
            ).exists()
        )


    # Abstract Methods That Need Implementation
    # -----------------------------------------------
    @abstractmethod
    def get_jobs_container_selector(self) -> Dict:
        """
        Define how to find the main container that holds all job listings.
        Returns:
        {
            'name': 'div',
            'attrs': {'class': 'jobs-container'}  # Example
        }
        """
        pass

    @abstractmethod
    def get_listings_selector(self) -> Dict:
        """ Define how to find individual job listings within the container. """ 
        pass

    @abstractmethod
    def get_listing_title_selector(self) -> Dict:
        """ Define how to find the title element within a job listing. """
        pass

    @abstractmethod
    def extract_job_link(self, job_listing: BeautifulSoup) -> str:
        """
        Extract job URL from the listing element.
        Args:
            job_listing: BeautifulSoup element containing the job listing
        Returns:
            Complete URL string (e.g., "https://example.com/jobs/123")
        """
        pass

    @abstractmethod
    def extract_company(self, soup: BeautifulSoup) -> str:
        """Extract company name from job details page."""
        pass

    @abstractmethod
    def extract_location(self, soup: BeautifulSoup) -> str:
        """Extract job location from job details page."""
        pass

    @abstractmethod
    def extract_operating_mode(self, soup: BeautifulSoup) -> str:
        """Extract job's operating mode from job details page."""
        pass

    @abstractmethod
    def extract_experience_level(self, soup: BeautifulSoup) -> str:
        """Extract job's experience from job details page."""
        
    
    @abstractmethod
    def extract_salary(self, soup: BeautifulSoup) -> str:
        """Extract salary information from job details page."""
        pass

    @abstractmethod
    def extract_description(self, soup: BeautifulSoup) -> str:
        """Extract job description from job details page."""
        pass

    @abstractmethod
    def get_skills_container_selector(self) -> Dict:
        """
        Define how to find the container that holds all skills.
        Returns:
        {
            'name': 'div',
            'attrs': {'id': 'skills-section'}  # Example
        }
        """
        pass

    @abstractmethod
    def has_skill_sections(self) -> bool:
        """
        Indicate if the website separates skills into required/nice-to-have sections.
        Returns:
            True if site has separate sections (like NoFluffJobs)
            False if site has single skills list (like JustJoinIT)
        """
        pass
    @abstractmethod
    def get_required_skills_selector(self) -> Dict:
        """
        Define how to find the required skills section.
        Only needed if has_skill_sections() returns True.
        """
        pass
    @abstractmethod
    def get_nice_skills_selector(self) -> Dict:
        """
        Define how to find the nice-to-have skills section.
        Only needed if has_skill_sections() returns True.
        """
        pass

    @abstractmethod
    def get_skill_item_selector(self) -> Dict:
        """Define how to find individual skill items within skills container."""
        pass

    @abstractmethod
    def extract_skill_name(self, element: BeautifulSoup) -> str:
        """
        Extract skill name from a skill element.
        Only needed if has_skill_sections() returns False.
        Args:
            element: BeautifulSoup element containing a single skill
        Returns:
            Skill name as string (e.g., "Python", "Docker")
        """
        pass

    @abstractmethod
    def extract_skill_level(self, element: BeautifulSoup) -> str:
        """
        Extract skill level from a skill element.
        Only needed if has_skill_sections() returns False.
        Args:
            element: BeautifulSoup element containing a single skill
        Returns:
            Skill level as string (e.g., "junior", "regular", "senior")
        """
        pass