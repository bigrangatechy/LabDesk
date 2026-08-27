//! Shared git clone/push progress snapshot for UI polling.

use std::sync::Mutex;

#[derive(Debug, Clone, Default)]
pub struct GitOpProgress {
    pub active: bool,
    /// `"clone"` or `"push"`.
    pub kind: String,
    pub project_id: Option<i64>,
    pub received_objects: usize,
    pub total_objects: usize,
    pub indexed_objects: usize,
    pub received_bytes: usize,
}

impl GitOpProgress {
    /// 0.0..=1.0 when totals are known; small nonzero while active with unknown total.
    pub fn fraction(&self) -> f64 {
        if !self.active {
            return 0.0;
        }
        if self.total_objects > 0 {
            let n = self.received_objects.max(self.indexed_objects);
            return (n as f64 / self.total_objects as f64).clamp(0.0, 1.0);
        }
        0.02
    }
}

static PROGRESS: Mutex<GitOpProgress> = Mutex::new(GitOpProgress {
    active: false,
    kind: String::new(),
    project_id: None,
    received_objects: 0,
    total_objects: 0,
    indexed_objects: 0,
    received_bytes: 0,
});

pub fn begin(kind: &str, project_id: Option<i64>) {
    if let Ok(mut g) = PROGRESS.lock() {
        *g = GitOpProgress {
            active: true,
            kind: kind.to_string(),
            project_id,
            received_objects: 0,
            total_objects: 0,
            indexed_objects: 0,
            received_bytes: 0,
        };
    }
}

pub fn on_transfer(
    received_objects: usize,
    total_objects: usize,
    indexed_objects: usize,
    received_bytes: usize,
) {
    if let Ok(mut g) = PROGRESS.lock() {
        if !g.active {
            return;
        }
        g.received_objects = received_objects;
        g.total_objects = total_objects;
        g.indexed_objects = indexed_objects;
        g.received_bytes = received_bytes;
    }
}

pub fn clear() {
    if let Ok(mut g) = PROGRESS.lock() {
        *g = GitOpProgress::default();
    }
}

pub fn snapshot() -> GitOpProgress {
    PROGRESS
        .lock()
        .map(|g| g.clone())
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fraction_with_totals() {
        clear();
        begin("clone", Some(42));
        on_transfer(50, 100, 40, 1024);
        let s = snapshot();
        assert!(s.active);
        assert_eq!(s.kind, "clone");
        assert_eq!(s.project_id, Some(42));
        assert_eq!(s.received_objects, 50);
        assert_eq!(s.total_objects, 100);
        assert!((s.fraction() - 0.5).abs() < 0.001);
        clear();
        let idle = snapshot();
        assert!(!idle.active);
        assert_eq!(idle.fraction(), 0.0);
        assert!(idle.project_id.is_none());
    }

    #[test]
    fn inactive_ignores_transfer_updates() {
        clear();
        on_transfer(10, 20, 5, 1);
        let s = snapshot();
        assert!(!s.active);
        assert_eq!(s.received_objects, 0);
        assert_eq!(s.fraction(), 0.0);
    }

    #[test]
    fn active_unknown_total_is_nonzero_fraction() {
        clear();
        begin("push", Some(7));
        on_transfer(0, 0, 0, 0);
        let s = snapshot();
        assert!(s.active);
        assert!(s.fraction() > 0.0);
        assert!(s.fraction() < 1.0);
        clear();
    }

    #[test]
    fn begin_resets_prior_stats() {
        clear();
        begin("clone", Some(1));
        on_transfer(99, 100, 99, 999);
        begin("push", Some(2));
        let s = snapshot();
        assert_eq!(s.kind, "push");
        assert_eq!(s.project_id, Some(2));
        assert_eq!(s.received_objects, 0);
        assert_eq!(s.total_objects, 0);
        clear();
    }
}
