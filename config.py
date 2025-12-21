# config for client types and target stakeholders

CLIENT_TYPES = {
    'Charter/K-12': {
        'keywords': ['charter', 'high school', 'k-12', 'k12', 'secondary', 'academy', 'prep'],
        'target_titles': [
            'CTE Director',
            'Instructional Technology Director',
            'Curriculum Coordinator',
            'Career Readiness Coordinator',
            'Principal',
            'Academic Dean',
            'Career Technical Education',
            'Technology Coordinator'
        ],
        'title_keywords': ['cte', 'career technical', 'instructional tech', 'curriculum', 
                          'career readiness', 'principal', 'academic dean']
    },
    
    'Undergraduate': {
        'keywords': ['university', 'college', 'undergraduate', 'bachelor'],
        'exclude_keywords': ['community college', 'technical college', 'law school'],
        'target_titles': [
            'Dean',
            'Associate Dean',
            'Program Director',
            'Academic Affairs',
            'Career Services Director',
            'Instructional Design',
            'Technology Training Coordinator'
        ],
        'title_keywords': ['dean', 'program director', 'academic affairs', 'career services',
                          'instructional design', 'technology training'],
        'departments': ['business', 'criminal justice', 'technology', 'computer science', 
                       'information systems', 'cybersecurity']
    },
    
    'Graduate/Business': {
        'keywords': ['mba', 'mpa', 'graduate school', 'business school', 'masters'],
        'target_titles': [
            'Graduate Program Director',
            'Associate Dean',
            'Faculty Director',
            'Experiential Learning Coordinator',
            'Career Development Director',
            'MBA Program Director',
            'MPA Program Director'
        ],
        'title_keywords': ['graduate', 'mba', 'mpa', 'associate dean', 'experiential learning',
                          'career development', 'program director'],
        'departments': ['mba', 'business', 'public administration', 'graduate studies']
    },
    
    'Technical College': {
        'keywords': ['technical college', 'community college', 'vocational', 'tech college'],
        'target_titles': [
            'Dean of Workforce Development',
            'Program Chair',
            'Instructional Technology',
            'Career & Technical Education Director',
            'Workforce Development Director',
            'CTE Director'
        ],
        'title_keywords': ['workforce development', 'program chair', 'instructional tech',
                          'career technical', 'cte', 'vocational'],
        'departments': ['workforce', 'technical', 'vocational', 'career']
    },
    
    'Continuing Education': {
        'keywords': ['continuing education', 'professional development', 'workforce training',
                    'executive education', 'certificate programs'],
        'target_titles': [
            'Director of Continuing Education',
            'Workforce Development Director',
            'Training Manager',
            'Program Coordinator',
            'Professional Development Director'
        ],
        'title_keywords': ['continuing education', 'workforce development', 'training manager',
                          'program coordinator', 'professional development']
    },
    
    'Law School': {
        'keywords': ['law school', 'school of law', 'college of law'],
        'target_titles': [
            'Law Library Director',
            'Associate Dean for Academic Affairs',
            'Legal Writing Director',
            'Experiential Learning Director',
            'Instructional Technology Librarian',
            'Dean of Students',
            'Assistant Dean'
        ],
        'title_keywords': ['law library', 'associate dean', 'legal writing', 'experiential learning',
                          'instructional tech', 'dean of students', 'assistant dean']
    },
    
    'Paralegal Program': {
        'keywords': ['paralegal', 'legal studies', 'legal assistant'],
        'target_titles': [
            'Paralegal Program Director',
            'Dean of Workforce Programs',
            'Legal Studies Faculty',
            'Program Chair',
            'Academic Affairs'
        ],
        'title_keywords': ['paralegal', 'legal studies', 'program director', 'program chair',
                          'workforce', 'academic affairs']
    },
    
    'Law Firm': {
        'keywords': ['law firm', 'legal services', 'attorneys', 'llp', 'pllc'],
        'target_titles': [
            'Director of Professional Development',
            'Director of Training',
            'Legal Operations',
            'Chief Talent Officer',
            'Learning & Development Manager',
            'HR Training Director',
            'Director of Attorney Development'
        ],
        'title_keywords': ['professional development', 'training', 'legal operations',
                          'talent officer', 'learning development', 'hr training',
                          'attorney development']
    }
}

def get_priority_score(title, client_type):
    """
    Score how well a title matches target decision makers
    Higher score = more relevant contact
    """
    if not title:
        return 0
    
    title_lower = title.lower()
    config = CLIENT_TYPES.get(client_type, {})
    keywords = config.get('title_keywords', [])
    
    score = 0
    
    # Exact target title match = highest priority
    target_titles = config.get('target_titles', [])
    for target in target_titles:
        if target.lower() in title_lower:
            score += 100
            break
    
    # Keyword matches
    for keyword in keywords:
        if keyword in title_lower:
            score += 10
    
    # Additional scoring for seniority
    if any(word in title_lower for word in ['director', 'dean', 'chief', 'vp', 'vice president']):
        score += 20
    
    # Penalize support staff titles
    if any(word in title_lower for word in ['assistant', 'secretary', 'clerk', 'admin']):
        score -= 30
    
    return max(score, 0)