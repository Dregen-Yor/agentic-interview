export interface EducationRecord {
    schoolName: string;
    degree: string;
    startDate: string | null; // Element Plus DatePicker 通常返回 YYYY-MM-DD 格式的字符串
    endDate: string | null;
    location?: string;
    courses?: string[];
  }
  
  export interface WorkExperienceRecord {
    companyName: string;
    jobTitle: string;
    startDate: string | null;
    endDate: string | null;
    location?: string;
    responsibilities?: string[];
    achievements?: string[];
    description?: string;
  }
  
  export interface ProjectExperienceRecord {
    projectName: string;
    description: string;
    startDate: string | null;
    endDate: string | null;
    techStack?: string[];
  }
  
  export interface CandidateRecord {
    userId?: number | null;
    name: string;
    email: string;
    phone: string;
    summary: string;
    educationHistory: EducationRecord[];
    workExperience: WorkExperienceRecord[];
    projectExperience: ProjectExperienceRecord[];
    skills: string[];
  }
  
  // CvRequest 对应后端的 VO
  export interface CvRequest {
    cv: string; // 原始简历文本，如果需要的话
    candidateRecord: CandidateRecord;
  }