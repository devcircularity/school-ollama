# rasa/actions/__init__.py
"""
Rasa Custom Actions Package
Organized by functionality: students, academic management, fees, guardians, and notifications
"""

# Import all student actions
from actions.student_actions import (
    ActionCreateStudent,
    ActionListStudents,
    ActionListStudentsByClass,
    ActionSearchStudent,
    ActionListUnassignedStudents,
    ActionAssignStudentToClass,
    ActionProvideAdmissionNumber,
    ActionAutoGenerateAdmission,
    ActionReenrollStudent,
    ActionShowUnassignedStudents,
    ActionGetStudentDetails,
    ValidateStudentCreationForm,
)

# Import all academic/class management actions
from actions.academic_actions import (
    ActionCreateAcademicYear,
    ActionCreateAcademicTerm,
    ActionCheckAcademicSetup,
    ActionGetCurrentAcademicYear,
    ActionGetCurrentTerm,
    ActionActivateAcademicYear,
    ActionDeactivateAcademicYear,
    ActionActivateTerm,
    ActionListAcademicTerms,
    ActionPromoteStudents,
    ActionCreateClass,
    ActionListClasses,
    ActionListEmptyClasses,
    ActionDeleteClass,
    ActionHelp,
    ActionCompleteTerm,
)

# Import all fee actions (keep these from existing fee_actions.py)
from actions.fee_actions import (
    ActionCreateFeeStructure,
    ActionListFeeStructures,
    ActionGenerateInvoices,
    ActionGetInvoice,
    ActionAddFeeItem,
    ActionViewFeeStructureDetails,
    ActionDeleteFeeItems,
    ActionDeleteSpecificFeeItem,
    ActionPublishFeeStructure,
    ActionSetDefaultFeeStructure,
    ActionSetStructureAsDefault,
    ActionIssueInvoices,
    ActionListInvoices,
    ActionListInvoicesByClass,
    ActionListUnpaidInvoices,
    ActionListStudentsWithBalances,  # NEW: Added this line
    ActionCancelInvoice,
    ActionRecordPayment,
    ActionSendPaymentNotification,
    ActionResetSlots,
    ActionNotifyParentsWithBalances,
    ActionBroadcastMessageToAllParents,
)

# Import guardian actions (keep these from existing guardian_actions.py)
from actions.guardian_actions import (
    ActionAddGuardian,
    ActionGetGuardians,
    ActionListStudentsWithoutGuardians,
    ActionSetPrimaryGuardian,
    ActionUpdateGuardian,
)

# Import notification actions (keep these from existing notification_actions.py)
from actions.notification_actions import (
    ActionNotifyPendingInvoices,
    ActionSendGuardianMessage,
)

from actions.school_info_actions import ActionGetSchoolInfo


# Make all actions discoverable by Rasa
__all__ = [
    # Student actions
    "ActionCreateStudent",
    "ActionListStudents",
    "ActionListStudentsByClass",
    "ActionSearchStudent",
    "ActionListUnassignedStudents",
    "ActionAssignStudentToClass",
    "ActionProvideAdmissionNumber",
    "ActionAutoGenerateAdmission",
    "ActionReenrollStudent",
    "ActionShowUnassignedStudents",
    "ActionGetStudentDetails",
    "ValidateStudentCreationForm",
    
    # Academic/Class management actions
    "ActionCreateAcademicYear",
    "ActionCreateAcademicTerm",
    "ActionCheckAcademicSetup",
    "ActionGetCurrentAcademicYear",
    "ActionGetCurrentTerm",
    "ActionActivateAcademicYear",
    "ActionDeactivateAcademicYear",
    "ActionActivateTerm",
    "ActionListAcademicTerms",
    "ActionPromoteStudents",
    "ActionCreateClass",
    "ActionListClasses",
    "ActionListEmptyClasses",
    "ActionDeleteClass",
    "ActionHelp",
    "ActionCompleteTerm",
    
    # Fee actions
    "ActionCreateFeeStructure",
    "ActionListFeeStructures",
    "ActionGenerateInvoices",
    "ActionGetInvoice",
    "ActionAddFeeItem",
    "ActionViewFeeStructureDetails",
    "ActionDeleteFeeItems",
    "ActionDeleteSpecificFeeItem",
    "ActionPublishFeeStructure",
    "ActionSetDefaultFeeStructure",
    "ActionSetStructureAsDefault",
    "ActionIssueInvoices",
    "ActionListInvoices",
    "ActionListInvoicesByClass",
    "ActionListUnpaidInvoices",
    "ActionListStudentsWithBalances",  # NEW: Added this line
    "ActionCancelInvoice",
    "ActionRecordPayment",
    "ActionSendPaymentNotification",
    "ActionResetSlots",
    "ActionNotifyParentsWithBalances",
    "ActionBroadcastMessageToAllParents",
    
    # Guardian actions
    "ActionAddGuardian",
    "ActionGetGuardians",
    "ActionListStudentsWithoutGuardians",
    "ActionSetPrimaryGuardian",
    "ActionUpdateGuardian",
    
    # Notification actions
    "ActionNotifyPendingInvoices",
    "ActionSendGuardianMessage",

    #school info actions
    "ActionGetSchoolInfo",
]