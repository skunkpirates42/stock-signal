function propertyName(member) {
  if (member.type !== "MemberExpression") return undefined;
  return member.computed ? member.property.value : member.property.name;
}

function isReaderCall(expression) {
  if (expression.type !== "CallExpression") return false;
  const callee = expression.callee;
  return (
    (callee.type === "Identifier" && /^read(?:[A-Z]|$)/.test(callee.name)) || isReaderCall(callee)
  );
}

function isResponseForward(expression) {
  return (
    expression.type === "CallExpression" &&
    propertyName(expression.callee) === "json" &&
    expression.callee.object.type === "Identifier" &&
    expression.callee.object.name === "Response"
  );
}

const requireResponseReader = {
  meta: {
    type: "problem",
    schema: [],
    messages: {
      readerRequired:
        "Pass awaited response.json() directly to a Read<T> reader from lib/. Server proxies may forward it through Response.json().",
    },
  },
  create(context) {
    return {
      CallExpression(node) {
        if (propertyName(node.callee) !== "json" || isResponseForward(node)) return;
        const awaited = node.parent;
        const consumer = awaited.parent;
        if (
          awaited.type === "AwaitExpression" &&
          consumer.arguments?.[0] === awaited &&
          (isReaderCall(consumer) || isResponseForward(consumer))
        )
          return;
        context.report({ node, messageId: "readerRequired" });
      },
    };
  },
};

export default requireResponseReader;
