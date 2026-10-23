import copy from "../../../locales/zh-hans.json";

// Swagger UI has no locale option. Only known interface controls are translated.
const labels = new Map<string, string>([
  ["Controls", copy.docs_swagger_controls],
  ["header.", copy.docs_swagger_header],
  ["Media Type", copy.docs_swagger_media_type],
  ["Copy path to clipboard", copy.docs_swagger_copy_path],
  ["authorization button unlocked", copy.docs_swagger_auth_unlocked],
  ["authorization button locked", copy.docs_swagger_auth_locked],
  ["Parameters", copy.docs_swagger_1],
  ["No parameters", copy.docs_swagger_2],
  ["Name", copy.docs_swagger_3],
  ["Description", copy.docs_swagger_4],
  ["Responses", copy.docs_swagger_5],
  ["Code", copy.docs_swagger_6],
  ["Details", copy.docs_swagger_7],
  ["Links", copy.docs_swagger_8],
  ["No links", copy.docs_swagger_9],
  ["Response body", copy.docs_swagger_10],
  ["Response headers", copy.docs_swagger_11],
  ["Request body", copy.docs_swagger_12],
  ["Example Value", copy.docs_swagger_13],
  ["Example", copy.docs_swagger_14],
  ["Examples", copy.docs_swagger_15],
  ["Schema", copy.docs_swagger_16],
  ["Schemas", copy.docs_swagger_17],
  ["Model", copy.docs_swagger_18],
  ["Models", copy.docs_swagger_19],
  ["Media type", copy.docs_swagger_20],
  ["Controls Accept header.", copy.docs_swagger_21],
  ["required", copy.docs_swagger_22],
  ["* required", copy.docs_swagger_23],
  ["deprecated", copy.docs_swagger_24],
  ["DEPRECATED", copy.docs_swagger_25],
  ["Deprecated", copy.docs_swagger_26],
  ["default", copy.docs_swagger_27],
  ["Default value", copy.docs_swagger_28],
  ["Available values", copy.docs_swagger_29],
  ["Authorize", copy.docs_swagger_30],
  ["Authorized", copy.docs_swagger_31],
  ["Available authorizations", copy.docs_swagger_32],
  ["Close", copy.docs_swagger_33],
  ["Logout", copy.docs_swagger_34],
  ["Value", copy.docs_swagger_35],
  ["Download", copy.docs_swagger_36],
  ["Download JSON", copy.docs_swagger_37],
  ["Expand all", copy.docs_swagger_38],
  ["Collapse all", copy.docs_swagger_39],
  ["Expand operation", copy.docs_swagger_40],
  ["Collapse operation", copy.docs_swagger_41],
  ["Copy to clipboard", copy.docs_swagger_42],
  ["Copied", copy.docs_swagger_43],
  ["Copy", copy.docs_swagger_44],
  ["Loading...", copy.docs_swagger_45],
  ["Failed to load API definition.", copy.docs_swagger_46],
  ["Errors", copy.docs_swagger_47],
  ["Hide", copy.docs_swagger_48],
  ["Show", copy.docs_swagger_49],
  ["Filter by tag", copy.docs_swagger_50],
]);

// Never traverse arbitrary descendants: parameter names, enum options, examples,
// schemas and Markdown may legitimately contain the same words as these labels.
const textControls = [
  ".opblock-section-header h4",
  ".opblock-section-header h4 > span",
  ".parameters-container .opblock-description-wrapper > p",
  ".parameters thead th",
  ".responses-table thead th",
  ".responses-table thead td",
  ".response-col_links > i",
  ".responses-inner > h4",
  ".tab > li > button",
  ".tab > li > a",
  ".models > h4 > button > span",
  ".btn.authorize > span",
  ".auth-btn-wrapper > button",
  ".auth-container > h4",
  ".auth-container label",
  ".dialog-ux .modal-ux-header > h3",
  ".response-control-media-type__title",
  ".response-control-media-type__accept-message",
  ".loading-container .loading > span",
  ".errors-wrapper > hgroup > h4",
  ".errors-wrapper > hgroup > button",
].join(", ");
const attributeControls = [
  "button.opblock-control-arrow",
  ".opblock-summary .copy-to-clipboard > button",
  "button.authorization__btn",
  "select.content-type",
  "button.models-control",
  "button.model-box-control",
  "button.copy-to-clipboard",
  ".operation-filter-input",
  ".dialog-ux button.close-modal",
].join(", ");

export function localizeSwagger(root: HTMLElement): MutationObserver {
  const translate = () => {
    for (const element of root.querySelectorAll(textControls)) {
      for (const node of element.childNodes) {
        if (node.nodeType !== Node.TEXT_NODE) continue;
        const source = node.textContent || "";
        const replacement = labels.get(source.trim());
        if (replacement)
          node.textContent = source.replace(source.trim(), replacement);
      }
    }
    for (const element of root.querySelectorAll(attributeControls)) {
      for (const attribute of ["aria-label", "title", "placeholder"]) {
        const replacement = labels.get(element.getAttribute(attribute) || "");
        if (replacement) element.setAttribute(attribute, replacement);
      }
    }
  };
  const observer = new MutationObserver(translate);
  observer.observe(root, {
    childList: true,
    subtree: true,
    characterData: true,
  });
  translate();
  return observer;
}

const root = document.getElementById("swagger-ui");
if (root) localizeSwagger(root);
