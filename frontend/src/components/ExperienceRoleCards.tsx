import type { ReactNode } from "react";
import type { CareerAchievement, CareerExperience, CareerProject } from "../api/types";

function dateRange(start?: string | null, end?: string | null) {
  if (!start && !end) return "";
  return [start, end || "Present"].filter(Boolean).join(" – ");
}

function Pills({ items }: { items: string[] }) {
  const unique = [...new Set(items.filter(Boolean))];
  if (!unique.length) return null;
  return (
    <div className="pill-list mt">
      {unique.map((item) => (
        <span className="pill" key={item}>{item}</span>
      ))}
    </div>
  );
}

export function ExperienceRoleCard({
  experience,
  projects,
  achievements,
  evidenceOpen,
  evidencePanel,
  onToggleEvidence,
  onEdit,
  onRemove,
  onVerify,
}: {
  experience: CareerExperience;
  projects: CareerProject[];
  achievements: CareerAchievement[];
  evidenceOpen: boolean;
  evidencePanel: ReactNode;
  onToggleEvidence: () => void;
  onEdit: () => void;
  onRemove: () => void;
  onVerify: () => void;
}) {
  const projectIds = new Set(projects.map((p) => p.id));
  const roleAchievements = achievements.filter(
    (a) => a.experience_id === experience.id && (!a.project_id || !projectIds.has(a.project_id)),
  );
  const underProject = (projectId: string) => achievements.filter((a) => a.project_id === projectId);

  return (
    <div className="role-card">
      <div className="row spread">
        <div>
          <div className="title">{experience.job_title} — {experience.organization}</div>
          <div className="meta">
            {[dateRange(experience.start_date, experience.end_date), experience.location, experience.employment_type]
              .filter(Boolean)
              .join(" · ")}
          </div>
        </div>
        <div className="row">
          {experience.verification_status && (
            <span className={`badge ${experience.verification_status}`}>
              {experience.verification_status.replace("_", " ")}
            </span>
          )}
          <button className="sm ghost" onClick={onToggleEvidence}>View Evidence</button>
          {experience.verification_status !== "verified" && (
            <button className="sm" onClick={onVerify}>Mark verified</button>
          )}
          <button className="sm" onClick={onEdit}>Edit</button>
          <button className="sm danger" onClick={onRemove}>Delete</button>
        </div>
      </div>
      {experience.description && <p className="role-desc">{experience.description}</p>}
      <Pills items={[...(experience.domains || []), ...(experience.technologies || [])]} />
      {evidenceOpen && evidencePanel}

      {!!projects.length && (
        <div className="role-nested">
          <div className="role-nested-label">Projects · {projects.length}</div>
          {projects.map((project) => {
            const nested = underProject(project.id);
            return (
              <div className="role-nested-item" key={project.id}>
                <div className="row spread">
                  <div>
                    <div className="role-nested-title">{project.name}</div>
                    <div className="meta">{[project.role, project.verification_status?.replace("_", " ")].filter(Boolean).join(" · ")}</div>
                  </div>
                </div>
                {project.description && <p className="role-desc">{project.description}</p>}
                <Pills items={project.technologies || []} />
                {!!(project.outcomes || []).length && (
                  <ul className="role-bullets">
                    {project.outcomes.map((o) => <li key={o}>{o}</li>)}
                  </ul>
                )}
                {nested.map((ach) => (
                  <div className="role-achievement" key={ach.id}>
                    <strong>{ach.title || ach.description.slice(0, 80)}</strong>
                    {ach.quantified_result && <span className="meta"> · {ach.quantified_result}</span>}
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      )}

      {!!roleAchievements.length && (
        <div className="role-nested">
          <div className="role-nested-label">Achievements · {roleAchievements.length}</div>
          {roleAchievements.map((ach) => (
            <div className="role-nested-item" key={ach.id}>
              <div className="role-nested-title">{ach.title || ach.description.slice(0, 90)}</div>
              {ach.quantified_result && <div className="meta">{ach.quantified_result}</div>}
              {ach.title && ach.description && <p className="role-desc">{ach.description}</p>}
              <Pills items={ach.skills || []} />
            </div>
          ))}
        </div>
      )}

      {!projects.length && !roleAchievements.length && (
        <p className="small muted mt">No projects or achievements linked to this role yet.</p>
      )}
    </div>
  );
}
