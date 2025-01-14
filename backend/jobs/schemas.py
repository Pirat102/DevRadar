from ninja import Schema, FilterSchema
from typing import Optional, List
from django.db.models import Q
from datetime import datetime, date


class ErrorSchema(Schema):
    message: str
    
class UserRegistrationSchema(Schema):
    username: str
    password: str
    email: Optional[str] = None

class JobSchema(Schema):
    id: int
    title: str
    company: Optional[str]
    location: Optional[str]
    operating_mode: Optional[str]
    salary: Optional[str]
    experience: Optional[str]
    skills: dict 
    url: str
    scraped_date: datetime
    summary: Optional[str]
    source: Optional[str]
    has_applied: bool = False
    application_id: Optional[int] = None
    
    @staticmethod
    def resolve_skills(obj):
        return obj.get_sorted_skills()
    

class JobFilterSchema(FilterSchema):
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    scraped_date: Optional[date] = None
    experience: Optional[str] = None
    operating_mode: Optional[str] = None
    salary: Optional[str] = None
    skills: Optional[List[str]] = None
    source: Optional[str] = None

    def filter_queryset(self, queryset):
        filters = {
            'title__icontains': self.title,
            'location__icontains': self.location,
            'scraped_date__gt': self.scraped_date,
            'experience__exact': self.experience,
            'operating_mode__exact': self.operating_mode,
            'source__exact': self.source
        }
        # Remove None values
        filters = {k: v for k, v in filters.items() if v is not None}
        queryset = queryset.filter(**filters)

        # Custom filter logic for skills (AND logic)
        if self.skills:
            skills_query = Q()
            for skill in self.skills:
                skills_query &= Q(skills__has_key=skill)
            queryset = queryset.filter(skills_query)
        
        return queryset
    
class ApplicationNoteSchema(Schema):
    id: Optional[int] = None
    content: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class JobApplicationSchema(Schema):
    id: int
    job: JobSchema
    applied_date: datetime
    status: str
    notes: List[ApplicationNoteSchema]
    
class UpdateStatusSchema(Schema):
    status: str
    
class CreateApplicationSchema(Schema):
    job_id: int
    
class CreateApplicationNoteSchema(Schema):
    content: str