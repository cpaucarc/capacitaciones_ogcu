  function convierteMayuscula(valor){
    valor.inputmask({regex: "[ A-Za-ñÑzäÄëËïÏöÖüÜáéíóúáéíóúÁÉÍÓÚÂÊÎÔÛâêîôûàèìòùÀÈÌÒÙ.-@]+", placeholder:''});
    valor.on("keypress", function () {
      valor=$(this);
      setTimeout(function () {
        valor.val(valor.val().toUpperCase());
     },50);
    });
  }
  convierteMayuscula($("#id_apellido_paterno"));
  convierteMayuscula($("#id_apellido_materno"));
  convierteMayuscula($("#id_nombres"));
  $("#id_celular").inputmask({
    regex: "^([0-9]{1,9})$"
  });
  $("#id_numero_documento").inputmask({
    regex: "^([0-9]{1,8})$"
  });