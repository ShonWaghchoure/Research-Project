"use client";

export function AttackSummary({ offText, onText }: { offText?: string; onText?: string }) {
  if (!offText && !onText) {
    return (
      <p className="text-sm text-text-muted">
        After both runs finish, a plain-language summary explains what the attacker gained and which
        defense limited it.
      </p>
    );
  }
  return (
    <div className="space-y-2 text-sm text-text">
      {offText && (
        <p>
          <span className="font-medium text-danger">Off: </span>
          {offText}
        </p>
      )}
      {onText && (
        <p>
          <span className="font-medium text-success">On: </span>
          {onText}
        </p>
      )}
    </div>
  );
}
