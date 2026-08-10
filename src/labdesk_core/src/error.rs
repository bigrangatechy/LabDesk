//! LabDesk error codes (`Docs/error-codes.md`).

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use thiserror::Error;

#[derive(Debug, Clone)]
pub struct ErrorInfo {
    pub code: &'static str,
    pub message: String,
    pub detail: Option<String>,
    pub retryable: bool,
}

impl ErrorInfo {
    pub fn new(code: &'static str, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
            detail: None,
            retryable: false,
        }
    }

    pub fn with_detail(mut self, detail: impl Into<String>) -> Self {
        self.detail = Some(detail.into());
        self
    }

    pub fn retryable(mut self) -> Self {
        self.retryable = true;
        self
    }

    pub fn to_py_err(&self) -> PyErr {
        let mut text = format!("[{}] {}", self.code, self.message);
        if let Some(detail) = &self.detail {
            text.push_str(": ");
            text.push_str(detail);
        }
        PyRuntimeError::new_err(text)
    }

    pub fn to_dict(&self, py: Python<'_>) -> PyResult<PyObject> {
        let dict = pyo3::types::PyDict::new(py);
        dict.set_item("code", self.code)?;
        dict.set_item("message", &self.message)?;
        dict.set_item("detail", self.detail.as_deref())?;
        dict.set_item("retryable", self.retryable)?;
        Ok(dict.into())
    }
}

impl std::fmt::Display for ErrorInfo {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "[{}] {}", self.code, self.message)?;
        if let Some(detail) = &self.detail {
            write!(f, ": {detail}")?;
        }
        Ok(())
    }
}

#[derive(Debug, Error)]
pub enum LabDeskError {
    #[error("{0}")]
    App(ErrorInfo),
}

impl LabDeskError {
    pub fn info(&self) -> &ErrorInfo {
        match self {
            Self::App(info) => info,
        }
    }

    pub fn cfg(code: &'static str, message: impl Into<String>) -> Self {
        Self::App(ErrorInfo::new(code, message))
    }

    pub fn auth(code: &'static str, message: impl Into<String>) -> Self {
        Self::App(ErrorInfo::new(code, message))
    }

    pub fn api(code: &'static str, message: impl Into<String>) -> Self {
        Self::App(ErrorInfo::new(code, message))
    }

    pub fn net(code: &'static str, message: impl Into<String>) -> Self {
        Self::App(ErrorInfo::new(code, message))
    }

    pub fn sys(code: &'static str, message: impl Into<String>) -> Self {
        Self::App(ErrorInfo::new(code, message))
    }
}

impl From<LabDeskError> for PyErr {
    fn from(err: LabDeskError) -> Self {
        err.info().to_py_err()
    }
}

pub type Result<T> = std::result::Result<T, LabDeskError>;
