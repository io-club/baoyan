# Shared application components

All business pages use Naive UI with one shared theme and the Chinese locale.
The only theme customization is the application primary color; component
padding, borders, fonts, focus states and disabled states use the library.
`public/console.css` contains page layout and business content styles rather
than overrides of buttons, native form controls, tables or Naive UI classes.

`src/components.js` supplies the shared presentation layer:

- NDataTable for paged results; existing DOM cell nodes are moved rather than
  cloned, retaining selection handlers and authenticated attachment previews.
- NInput, NInputNumber, NDatePicker, NSelect, NCheckbox and NUpload for forms
  and filters. Original named form controls retain the business values while
  the visible controls are actual Naive UI components. Programmatic value and
  checkbox changes are synchronized with the visible control.
- NModal/NFormItem for shared editors and task logs, NDialog for confirmation,
  and NMessage for operation feedback.
- NCard/NStatistic, NTag, NProgress and NEmpty for content and status.

The calendar uses the same theme and controls directly. Its date grid and
milestone colors are domain-specific layout; tag color selection is NColorPicker.
Pagination continues to use NPagination with server-side offsets. The Agent
retains the vendor iframe at full viewport height.

Local browser verification covers all six remaining business pages, shared
editors, password masking, actual mentor saves, confirmation/cancellation,
file upload/download byte equality, intel selection synchronization and task
log polling stopping when its modal closes. Fixtures are removed after checks.

Task refresh retains the table and pager instances. Rows use task UUID keys;
only changed cells and statistics are patched, preserving scroll and focus.
Out-of-order responses are ignored after a newer request or route change.
Browser verification checks real eight-second polling and manual refresh
on page two, with changed response data and a scrolled/focused task list.
